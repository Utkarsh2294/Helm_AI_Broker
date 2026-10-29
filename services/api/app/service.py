"""Transactional control plane. Agents cannot approve, publish or mutate state."""
from datetime import datetime, timedelta
import asyncio
from sqlalchemy import select

from app.agents.quotation import build_rfq
from app.agents.runtime import run_agent
from app.config import settings
from app.db.models import Activity, Approval, Case, Job, ModelProposal, Publication, Snapshot, uid, utcnow
from app.db.store import audit, latest, save_snapshot, verify_chain
from app.schemas import DNR, DomainError, QuoteRequest, State
from app.publication import process_publication


def invoke(kind, payload):
    return run_agent(kind, payload, settings().agent_runtime)


def get_case(db, case_id):
    case = db.scalar(select(Case).where(Case.id == case_id).with_for_update())
    if not case:
        raise DomainError("Case not found", 404)
    return case


def transition(db, case, expected, target, event_type, actor, payload=None):
    if case.state not in expected:
        raise DomainError(f"Action unavailable while case is {case.state}")
    if actor.startswith("agent:") and target in (State.PUBLISHED, State.AWAIT_BROKER_RELEASE, State.QUOTES_PENDING):
        audit(db, case.id, "gate_violation", actor)
        db.commit()
        raise DomainError("An agent cannot approve advice", 403)
    before = case.state
    case.state = target
    audit(db, case.id, event_type, actor, {"from": before, "to": target, **(payload or {})})


def import_request(db, request: QuoteRequest):
    existing = db.scalar(select(Case).where(Case.core_request_id == request.id))
    if existing:
        return existing
    case = Case(core_request_id=request.id, profile={"name": request.name, "cover_type": request.cover_type,
                                                     "postcode": request.postcode_district})
    db.add(case)
    db.flush()
    save_snapshot(db, case.id, "request", request.model_dump())
    audit(db, case.id, "request_received", "system")
    transition(db, case, [State.RECEIVED], State.INTAKE_RUNNING, "intake_started", "system")
    result = invoke("intake", request.model_dump())
    save_snapshot(db, case.id, "dnr", result)
    target = State.NEEDS_INFO if result["missing"] else State.FACTFIND_REVIEW
    if result["vulnerability_flags"]:
        target = State.PAUSED_NEEDS_HUMAN
        case.previous_state = State.FACTFIND_REVIEW
    transition(db, case, [State.INTAKE_RUNNING], target, "intake_completed", "agent:1")
    return case


def require_broker(user):
    if user.role not in ("authorised_broker", "lead_broker"):
        raise DomainError("This action requires a broker", 403)


def act(db, case_id, action, user, session, body):
    case = get_case(db, case_id)
    if action == "sign-off" and user.role == "broker_assistant":
        pass
    else:
        require_broker(user)
    actor = f"broker:{user.id}"
    if action == "pause":
        if case.state in [State.PUBLISHED, State.CLOSED, State.COMPLAINT_FLAGGED, State.PAUSED_NEEDS_HUMAN]:
            raise DomainError("This case cannot be paused")
        case.previous_state = case.state
        transition(db, case, [case.state], State.PAUSED_NEEDS_HUMAN, "broker_paused", actor)
    elif action == "resume":
        if db.scalar(select(Job).where(Job.case_id == case.id, Job.status == "needs_human")):
            raise DomainError("Resolve the partner exception before resuming")
        target = case.previous_state or State.FACTFIND_REVIEW
        transition(db, case, [State.PAUSED_NEEDS_HUMAN], target, "broker_resumed", actor)
    elif action == "resolve":
        if case.state not in (State.PAUSED_NEEDS_HUMAN, State.UW_REFERRAL):
            raise DomainError("No exception is awaiting resolution")
        if case.state == State.UW_REFERRAL:
            if settings().partner_mode != "simulator" or len(body.get("underwriter_reference", "")) < 3:
                raise DomainError("G3 requires a recorded fictional underwriter confirmation; live referrals need partner evidence")
            db.add(Approval(case_id=case.id, gate="G3", user_id=user.id, payload_hash=latest(db, case.id, "rfq").body_hash))
            save_snapshot(db, case.id, "referral_resolution", {"underwriter_reference": body["underwriter_reference"], "by": user.id})
        jobs = db.scalars(select(Job).where(Job.case_id == case.id, Job.status == "needs_human")).all()
        if not jobs:
            raise DomainError("Use Resume after reviewing the ranking exception")
        for job in jobs:
            job.body = {"scenario": "happy"}
            job.status = "pending"
            job.due_at = utcnow().isoformat()
        transition(db, case, [State.PAUSED_NEEDS_HUMAN, State.UW_REFERRAL], State.QUOTES_PENDING,
                   "broker_resolved_demo_partner_exception", actor)
    elif action == "complaint":
        if case.state in [State.CLOSED, State.COMPLAINT_FLAGGED]:
            raise DomainError("Complaint already flagged or case closed")
        case.previous_state = case.state
        transition(db, case, [case.state], State.COMPLAINT_FLAGGED, "complaint_flagged", actor)
    elif action == "assign":
        case.assigned_to = user.id
        audit(db, case.id, "case_assigned", actor)
    elif action == "sign-off":
        if case.state != State.FACTFIND_REVIEW:
            raise DomainError("Fact-find is not ready for sign-off")
        dnr = latest(db, case.id, "dnr")
        data = DNR.model_validate(dnr.body)
        if not body.get("dnr_acknowledged") or (data.vulnerability_flags and not body.get("vulnerability_acknowledged")):
            raise DomainError("Explicitly acknowledge the fact-find and any vulnerability indicators", 422)
        if data.missing or not data.consent_to_share:
            raise DomainError("Fact-find has missing information or consent")
        db.add(Approval(case_id=case.id, gate="G0", user_id=user.id, payload_hash=dnr.body_hash))
        transition(db, case, [State.FACTFIND_REVIEW], State.RFQ_DRAFTING,
                   "dnr_signed_off", actor, {"dnr_hash": dnr.body_hash})
        transition(db, case, [State.RFQ_DRAFTING], State.RFQ_RELEASE_CHECK, "rfq_drafted", "system")
        transition(db, case, [State.RFQ_RELEASE_CHECK], State.AWAIT_BROKER_RELEASE, "release_check_completed", "system")
    elif action == "release":
        if case.state != State.AWAIT_BROKER_RELEASE:
            raise DomainError("Sign off the fact-find first")
        snapshot = latest(db, case.id, "dnr")
        dnr = DNR.model_validate(snapshot.body)
        g0 = db.scalar(select(Approval).where(Approval.case_id == case.id, Approval.gate == "G0",
                                             Approval.payload_hash == snapshot.body_hash))
        medical_ok = bool(body.get("medical_released"))
        rfq = build_rfq(dnr, signed_off=bool(g0), medical_released=medical_ok)
        db.add(Approval(case_id=case.id, gate="G1", user_id=user.id, payload_hash=snapshot.body_hash))
        save_snapshot(db, case.id, "rfq", rfq.model_dump(mode="json"))
        db.add(Job(case_id=case.id, kind="collect_quotes", due_at=(utcnow() + timedelta(
            seconds=settings().demo_delay_seconds if settings().clock_mode == "demo" else 21600)).isoformat(), body={"scenario": body.get("scenario", "happy")}))
        for number in (1, 2):
            db.add(Job(case_id=case.id, kind="chase", due_at=(utcnow() + timedelta(seconds=number * (2 if settings().clock_mode == "demo" else 7200))).isoformat(), body={"chase_number": number}))
        transition(db, case, [State.AWAIT_BROKER_RELEASE], State.QUOTES_PENDING, "rfq_released", actor)
    elif action == "selection":
        if case.state != State.BROKER_REVIEW:
            raise DomainError("Ranking is not ready for selection")
        dnr, ranking = latest(db, case.id, "dnr"), latest(db, case.id, "ranking")
        if body.get("ranking_id") != ranking.body["id"]:
            raise DomainError("The ranking changed; refresh before selecting")
        transition(db, case, [State.BROKER_REVIEW], State.SUITABILITY_DRAFT, "review_started", actor)
        pack = invoke("review", {"dnr": dnr.body, "ranking": ranking.body, **body})
        save_snapshot(db, case.id, "pack", pack)
        save_snapshot(db, case.id, "selection", {"selected": body["selected"], "survey": body["survey"],
                                                "ranking_id": ranking.body["id"]})
        if any(value == "down" for value in body["survey"]["thumbs"].values()):
            from app.db.platform import EdgeCase
            db.add(EdgeCase(case_id=case.id, selection_id=latest(db, case.id, "selection").id,
                            body={"ranking_id": ranking.body["id"], "survey": body["survey"], "summary": "Disputed ranking feedback requires human review"}))
        transition(db, case, [State.SUITABILITY_DRAFT], State.AWAIT_APPROVAL, "pack_drafted", "agent:4")
        audit(db, case.id, "selection_submitted", actor, {"pack_hash": pack["pack_hash"]})
    elif action == "request-changes":
        transition(db, case, [State.AWAIT_APPROVAL], State.BROKER_REVIEW, "changes_requested", actor)
    elif action == "approve":
        if not user.can_approve or user.role != "authorised_broker" or not user.fca_irn:
            raise DomainError("Only an authorised adviser may approve advice", 403)
        if not session.step_up_at or utcnow() - datetime.fromisoformat(session.step_up_at) > timedelta(minutes=5):
            raise DomainError("Re-authenticate before approval", 401, requires_step_up=True)
        from app.auth.mfa import load_challenge
        step_up = load_challenge(db, body.get("step_up_token", ""), "step-up")
        if step_up.user_id != user.id or step_up.body.get("session_id") != session.id:
            raise DomainError("Step-up belongs to a different session", 403)
        if case.state != State.AWAIT_APPROVAL:
            raise DomainError("No pack is awaiting approval")
        pack = latest(db, case.id, "pack").body
        if body.get("pack_hash") != pack["pack_hash"]:
            raise DomainError("Pack changed; review the latest version")
        from app.compliance.pack_validator import validate_pack
        validate_pack(pack)
        if set(pack.get("dnr_sections_confirmed", [])) != {"priorities", "coverage", "budget", "household", "medical_flag"}:
            raise DomainError("Review and confirm every DNR reference section before approval", 422)
        if set(pack.get("unmet_needs_addressed", [])) != {f"{item['plan_id']}:{item['need']}" for item in pack["unmet_needs"]}:
            raise DomainError("Address every unmet need before approval", 422)
        step_up.consumed = True
        approval = Approval(case_id=case.id, gate="G2", user_id=user.id, payload_hash=pack["pack_hash"],
                            step_up_at=session.step_up_at)
        db.add(approval)
        db.flush()
        if pack.get("commission_deviation"):
            audit(db, case.id, "commission_deviation", actor, pack["commission_diagnostic"])
        if settings().core_delivery_enabled:
            db.add(Job(case_id=case.id, kind="publish", due_at=utcnow().isoformat(),
                       body={"approval_id": approval.id, "pack_hash": pack["pack_hash"], "attempts": 0}))
            audit(db, case.id, "publication_queued", actor, {"approval_id": approval.id})
        else:
            db.add(Publication(case_id=case.id, approval_id=approval.id, pack_hash=pack["pack_hash"]))
            transition(db, case, [State.AWAIT_APPROVAL], State.PUBLISHED, "demo_recommendation_delivered", actor,
                       {"approval_id": approval.id, "pack_hash": pack["pack_hash"]})
    else:
        raise DomainError("Unknown action", 404)
    db.flush()
    return detail(db, case)


def process_due_jobs(db):
    if settings().agents_paused:
        return
    jobs = db.scalars(select(Job).where(Job.status == "pending", Job.due_at <= utcnow().isoformat()).order_by(Job.due_at)
                      .with_for_update(skip_locked=True)).all()
    for job in jobs:
        case = get_case(db, job.case_id)
        if case.state in (State.PAUSED_NEEDS_HUMAN, State.COMPLAINT_FLAGGED):
            continue
        if job.kind == "publish":
            process_publication(db, case, job)
            continue
        if case.state != State.QUOTES_PENDING:
            job.status = "cancelled"
            continue
        if job.kind == "chase":
            audit(db, case.id, "partner_chase", "agent:2", {"chase_number": job.body["chase_number"]})
            job.status = "completed"
            continue
        rfq = latest(db, case.id, "rfq").body
        from app.partners import PartnerGateway
        from app.agents.quotation import RFQ
        replies = asyncio.run(PartnerGateway().collect(RFQ.model_validate(rfq), job.body["scenario"]))
        save_snapshot(db, case.id, "quotes", replies)
        special = [p for p in replies["partners"] if p["state"] in ("clarification", "referred")]
        if special:
            case.previous_state = State.QUOTES_PENDING
            transition(db, case, [State.QUOTES_PENDING], State.UW_REFERRAL if special[0]["state"] == "referred" else State.PAUSED_NEEDS_HUMAN, "partner_requires_human",
                       "agent:2", {"reason": "G3" if special[0]["state"] == "referred" else "H5"})
            job.status = "needs_human"
            continue
        dnr = latest(db, case.id, "dnr").body
        transition(db, case, [State.QUOTES_PENDING], State.QUOTES_COLLECTED, "quotes_collected", "agent:2")
        transition(db, case, [State.QUOTES_COLLECTED], State.RANKING, "ranking_started", "system")
        from app.shadow import rank_with_models
        ranking = rank_with_models(db, {"dnr": dnr, "quotes": replies["quotes"], "id": uid(),
                                       "case_id": case.id, "tax_rate": settings().ipt_rate})
        save_snapshot(db, case.id, "ranking", ranking)
        if ranking["needs_human"] or len(ranking["top"]) < 3:
            case.previous_state = State.BROKER_REVIEW
            transition(db, case, [State.RANKING], State.PAUSED_NEEDS_HUMAN, "ranking_requires_human",
                       "agent:3", {"reason": "H3" if ranking["needs_human"] else "insufficient_quotes"})
        else:
            transition(db, case, [State.RANKING], State.BROKER_REVIEW, "ranking_completed", "agent:3")
        job.status = "completed"


def learning_run(db):
    records = []
    consumed = set()
    for proposal in db.scalars(select(ModelProposal).where(ModelProposal.status == "proposed")):
        consumed.update(proposal.body.get("selection_ids", []))
    # Keep the latest preference per case so repeated draft edits do not multiply the evidence.
    selections = {}
    for selection in db.scalars(select(Snapshot).where(Snapshot.kind == "selection").order_by(Snapshot.version)):
        selections[selection.case_id] = selection
    for selection in selections.values():
        if selection.id in consumed:
            continue
        ranking = db.scalar(select(Snapshot).where(Snapshot.case_id == selection.case_id,
                                                   Snapshot.kind == "ranking").order_by(Snapshot.version.desc()))
        if ranking and ranking.body["id"] == selection.body["ranking_id"]:
            records.append({"id": selection.id, "case_id": selection.case_id,
                            "ranking": ranking.body, **selection.body})
    result = invoke("learning", {"records": records})
    result["selection_ids"] = [record["id"] for record in records]
    proposal = ModelProposal(body=result, status=result["status"])
    db.add(proposal)
    db.flush()
    return {"id": proposal.id, **result}


def detail(db, case):
    data = {"id": case.id, "core_request_id": case.core_request_id, **case.profile,
            "state": case.state, "assigned_to": case.assigned_to, "created_at": case.created_at,
            "version": case.version}
    for kind in ("dnr", "rfq", "quotes", "ranking", "pack", "publication"):
        snapshot = latest(db, case.id, kind)
        data[kind] = snapshot.body if snapshot else None
    data["events"] = [{k: getattr(row, k) for k in ("seq", "actor", "type", "payload", "created_at", "hash")}
                      for row in db.scalars(select(Activity).where(Activity.case_id == case.id).order_by(Activity.seq))]
    return data


def evidence(db, case):
    events = db.scalars(select(Activity).where(Activity.case_id == case.id).order_by(Activity.seq)).all()
    return {"case": detail(db, case), "chain_valid": verify_chain(events),
            "approvals": [{k: getattr(a, k) for k in
                           ("id", "gate", "user_id", "payload_hash", "created_at", "step_up_at")}
                          for a in db.scalars(select(Approval).where(Approval.case_id == case.id))],
            "snapshots": [{"id": s.id, "kind": s.kind, "version": s.version,
                           "body_hash": s.body_hash, "body": s.body}
                          for s in db.scalars(select(Snapshot).where(Snapshot.case_id == case.id))]}
