"""Transactional control plane. Agents cannot approve, publish or mutate state."""

from datetime import datetime, timedelta
import asyncio
from httpx import HTTPError
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
    if db.info.get("staff_user"):
        from app.case_access import require_case_access

        require_case_access(case, db.info["staff_user"])
    return case


def transition(db, case, expected, target, event_type, actor, payload=None):
    if case.state not in expected:
        raise DomainError(f"Action unavailable while case is {case.state}")
    if actor.startswith("agent:") and target in (
        State.RFQ_DRAFTING,
        State.PUBLISHED,
        State.AWAIT_BROKER_RELEASE,
        State.QUOTES_PENDING,
    ):
        audit(db, case.id, "GATE_VIOLATION", actor)
        db.commit()
        raise DomainError("An agent cannot approve advice", 403)
    from app.case_graph import permits

    if not permits(case.state, target, event_type):
        raise DomainError(f"Invalid case transition: {case.state} to {target}")
    gate = (
        "G0"
        if target == State.RFQ_DRAFTING
        else "G1"
        if target == State.QUOTES_PENDING and case.state == State.AWAIT_BROKER_RELEASE
        else None
    )
    if gate:
        snapshot = latest(db, case.id, "dnr")
        if not snapshot or not db.scalar(
            select(Approval).where(
                Approval.case_id == case.id,
                Approval.gate == gate,
                Approval.payload_hash == snapshot.body_hash,
            )
        ):
            raise DomainError(f"{gate} evidence is required for this transition", 403)
    if target == State.PUBLISHED and not db.scalar(select(Publication).where(Publication.case_id == case.id)):
        raise DomainError("Delivery acknowledgement and human approval are required before publication", 403)
    before = case.state
    case.state = target
    audit(db, case.id, event_type, actor, {"from": before, "to": target, **(payload or {})})


def import_request(db, request: QuoteRequest):
    from app.compliance.medical_ambiguity import check_medical_ambiguity
    from app.agents.intake import research_request

    existing = db.scalar(select(Case).where(Case.core_request_id == request.id))
    if existing:
        return existing
    case = Case(
        core_request_id=request.id,
        profile={
            "name": request.name,
            "cover_type": request.cover_type,
            "postcode": request.postcode_district,
        },
    )
    db.add(case)
    db.flush()
    save_snapshot(db, case.id, "request", request.model_dump())
    audit(db, case.id, "request_received", "system")
    transition(db, case, [State.RECEIVED], State.INTAKE_RUNNING, "intake_started", "system")
    medical_halt = check_medical_ambiguity(request.model_dump())
    result = (
        research_request(request).model_dump(mode="json")
        if medical_halt
        else invoke("intake", request.model_dump())
    )
    save_snapshot(db, case.id, "dnr", result)
    target = State.NEEDS_INFO if result["missing"] else State.FACTFIND_REVIEW
    if result["vulnerability_flags"] or medical_halt:
        case.priority = "urgent"
        target = State.PAUSED_NEEDS_HUMAN
        case.previous_state = State.FACTFIND_REVIEW
    if medical_halt:
        save_snapshot(db, case.id, "medical_triage", medical_halt)
        audit(db, case.id, "medical_review_required", "firewall", medical_halt)
    transition(db, case, [State.INTAKE_RUNNING], target, "intake_completed", "agent:1")
    return case


def require_broker(user):
    if user.role not in ("authorised_broker", "lead_broker"):
        raise DomainError("This action requires a broker", 403)


def act(db, case_id, action, user, session, body):
    case = get_case(db, case_id)
    if (action == "sign-off" and user.role == "broker_assistant") or (
        action == "complaint" and user.role == "compliance_officer"
    ):
        pass
    else:
        require_broker(user)
    actor = f"broker:{user.id}"
    if action == "pause":
        if case.state in [State.PUBLISHED, State.CLOSED, State.COMPLAINT_FLAGGED, State.PAUSED_NEEDS_HUMAN]:
            raise DomainError("This case cannot be paused")
        if case.state == State.AWAIT_BROKER_RELEASE and len(body.get("reason", "").strip()) < 10:
            raise DomainError("Record a release pause reason of at least 10 characters", 422)
        save_snapshot(
            db,
            case.id,
            "broker_pause",
            {"reason": body.get("reason", "").strip(), "by": user.id, "from": case.state},
        )
        case.previous_state = case.state
        transition(db, case, [case.state], State.PAUSED_NEEDS_HUMAN, "broker_paused", actor)
    elif action == "resume":
        from app.compliance.medical_ambiguity import pending_review

        if pending_review(db, case.id):
            raise DomainError("Record the medical wording review before resuming", 409)
        if db.scalar(select(Job).where(Job.case_id == case.id, Job.status == "needs_human")):
            raise DomainError("Resolve the partner exception before resuming")
        target = case.previous_state or State.FACTFIND_REVIEW
        transition(db, case, [State.PAUSED_NEEDS_HUMAN], target, "broker_resumed", actor)
    elif action == "resolve":
        if case.state not in (State.PAUSED_NEEDS_HUMAN, State.UW_REFERRAL):
            raise DomainError("No exception is awaiting resolution")
        if case.state == State.UW_REFERRAL or case.previous_state == State.UW_REFERRAL:
            if settings().partner_mode != "simulator" or len(body.get("underwriter_reference", "")) < 3:
                raise DomainError(
                    "G3 requires a recorded fictional underwriter confirmation; live referrals need partner evidence"
                )
            db.add(
                Approval(
                    case_id=case.id,
                    gate="G3",
                    user_id=user.id,
                    payload_hash=latest(db, case.id, "rfq").body_hash,
                )
            )
            save_snapshot(
                db,
                case.id,
                "referral_resolution",
                {"underwriter_reference": body["underwriter_reference"], "by": user.id},
            )
        jobs = db.scalars(select(Job).where(Job.case_id == case.id, Job.status == "needs_human")).all()
        if not jobs:
            raise DomainError("Use Resume after reviewing the ranking exception")
        for job in jobs:
            job.body = {"scenario": "happy"}
            job.status = "pending"
            job.due_at = utcnow().isoformat()
        transition(
            db,
            case,
            [State.PAUSED_NEEDS_HUMAN, State.UW_REFERRAL],
            State.QUOTES_PENDING,
            "broker_resolved_demo_partner_exception",
            actor,
        )
    elif action == "complaint":
        from app.complaints import open_complaint

        open_complaint(db, case, actor, body.get("reason", ""))
    elif action == "assign":
        case.assigned_to = user.id
        audit(db, case.id, "case_assigned", actor)
    elif action == "sign-off":
        from app.compliance.medical_ambiguity import pending_review

        if pending_review(db, case.id):
            raise DomainError("Medical wording review is still required", 409)
        if case.state != State.FACTFIND_REVIEW:
            raise DomainError("Fact-find is not ready for sign-off")
        dnr = latest(db, case.id, "dnr")
        data = DNR.model_validate(dnr.body)
        if not body.get("dnr_acknowledged") or (
            data.vulnerability_flags and not body.get("vulnerability_acknowledged")
        ):
            raise DomainError("Explicitly acknowledge the fact-find and any vulnerability indicators", 422)
        if data.missing or not data.consent_to_share:
            raise DomainError("Fact-find has missing information or consent")
        if not data.record:
            from app.agents.intake import research_request

            source = QuoteRequest.model_validate(latest(db, case.id, "request").body)
            data.record = research_request(source).record
            data.record.stated_needs = [
                {"category": key, "detail": str(value), "source": "broker-reviewed"}
                for key, value in data.needs.model_dump().items()
            ]
        data.record.broker_ref, data.record.budget_confirmed = user.id, True
        data.version = dnr.version + 1
        dnr = save_snapshot(db, case.id, "dnr", data.model_dump(mode="json"))
        db.add(Approval(case_id=case.id, gate="G0", user_id=user.id, payload_hash=dnr.body_hash))
        transition(
            db,
            case,
            [State.FACTFIND_REVIEW],
            State.RFQ_DRAFTING,
            "dnr_signed_off",
            actor,
            {"dnr_hash": dnr.body_hash},
        )
        transition(db, case, [State.RFQ_DRAFTING], State.RFQ_RELEASE_CHECK, "rfq_drafted", "system")
        transition(
            db,
            case,
            [State.RFQ_RELEASE_CHECK],
            State.AWAIT_BROKER_RELEASE,
            "release_check_completed",
            "system",
        )
    elif action == "release":
        if case.state != State.AWAIT_BROKER_RELEASE:
            raise DomainError("Sign off the fact-find first")
        snapshot = latest(db, case.id, "dnr")
        dnr = DNR.model_validate(snapshot.body)
        g0 = db.scalar(
            select(Approval).where(
                Approval.case_id == case.id,
                Approval.gate == "G0",
                Approval.payload_hash == snapshot.body_hash,
            )
        )
        medical_ok = bool(body.get("medical_released"))
        from app.partners import active_partners

        eligible = active_partners(db, dnr)
        if len(eligible) < settings().minimum_active_partners:
            case.previous_state = case.state
            transition(
                db,
                case,
                [case.state],
                State.PAUSED_NEEDS_HUMAN,
                "partner_panel_unavailable",
                actor,
                {"reason": "insufficient_active_partners", "code": "H7"},
            )
            return detail(db, case)
        rfq = build_rfq(
            dnr, signed_off=bool(g0), medical_released=medical_ok, partner_ids=[p.id for p in eligible]
        )
        db.add(Approval(case_id=case.id, gate="G1", user_id=user.id, payload_hash=snapshot.body_hash))
        save_snapshot(db, case.id, "rfq", rfq.model_dump(mode="json"))
        db.add(
            Job(
                case_id=case.id,
                kind="collect_quotes",
                due_at=(rfq.deadline if settings().partner_mode == "simulator" else utcnow()).isoformat(),
                body={"scenario": body.get("scenario", "happy")},
            )
        )
        for number in (1, 2):
            from app.clock import get_clock

            db.add(
                Job(
                    case_id=case.id,
                    kind="chase",
                    due_at=(utcnow() + get_clock().wall_delay(timedelta(hours=2 * number))).isoformat(),
                    body={"chase_number": number},
                )
            )
        db.add(Job(case_id=case.id, kind="rfq_timeout", due_at=rfq.deadline.isoformat(), body={}))
        transition(db, case, [State.AWAIT_BROKER_RELEASE], State.QUOTES_PENDING, "rfq_released", actor)
    elif action == "selection":
        if case.state != State.BROKER_REVIEW:
            raise DomainError("Ranking is not ready for selection")
        dnr, ranking = latest(db, case.id, "dnr"), latest(db, case.id, "ranking")
        if body.get("ranking_id") != ranking.body["id"]:
            raise DomainError("The ranking changed; refresh before selecting")
        from app.plan_ratings import validate_reviews, reviews_hash, public

        reviews = validate_reviews(db, case.id, ranking.body, user, body["selected"])
        transition(db, case, [State.BROKER_REVIEW], State.SUITABILITY_DRAFT, "review_started", actor)
        pack = invoke("review", {"dnr": dnr.body, "ranking": ranking.body, **body})
        from app.agents.review import canonical_hash

        pack = {key: value for key, value in pack.items() if key != "pack_hash"}
        pack.update(
            {
                "broker_ratings": [public(row) for row in reviews],
                "ratings_hash": reviews_hash(reviews),
                "ratings_broker_id": user.id,
            }
        )
        pack["pack_hash"] = canonical_hash(pack)
        save_snapshot(db, case.id, "pack", pack)
        save_snapshot(
            db,
            case.id,
            "selection",
            {
                "selected": body["selected"],
                "survey": body["survey"],
                "ranking_id": ranking.body["id"],
                "broker_ratings": [public(row) for row in reviews],
            },
        )
        if any(value == "down" for value in body["survey"]["thumbs"].values()):
            from app.db.platform import EdgeCase

            db.add(
                EdgeCase(
                    case_id=case.id,
                    selection_id=latest(db, case.id, "selection").id,
                    body={
                        "ranking_id": ranking.body["id"],
                        "survey": body["survey"],
                        "summary": "Disputed ranking feedback requires human review",
                    },
                )
            )
        transition(db, case, [State.SUITABILITY_DRAFT], State.AWAIT_APPROVAL, "pack_drafted", "agent:4")
        audit(db, case.id, "selection_submitted", actor, {"pack_hash": pack["pack_hash"]})
    elif action == "request-changes":
        transition(db, case, [State.AWAIT_APPROVAL], State.BROKER_REVIEW, "changes_requested", actor)
    elif action == "approve":
        if not user.can_approve or user.role != "authorised_broker" or not user.fca_irn:
            raise DomainError("Only an authorised adviser may approve advice", 403)
        if case.state != State.AWAIT_APPROVAL:
            raise DomainError("No pack is awaiting approval")
        pack = latest(db, case.id, "pack").body
        from app.plan_ratings import validate_reviews, reviews_hash

        ranking_snapshot = latest(db, case.id, "ranking")
        if not ranking_snapshot or not pack.get("selected"):
            raise DomainError("Incomplete advice evidence cannot be approved", 403)
        reviews = validate_reviews(db, case.id, ranking_snapshot.body, user, pack["selected"])
        if pack.get("ratings_broker_id") != user.id or pack.get("ratings_hash") != reviews_hash(reviews):
            raise DomainError("Assessments changed. Rebuild and review the recommendation pack.", 409)
        if not session.step_up_at or utcnow() - datetime.fromisoformat(session.step_up_at) > timedelta(
            minutes=5
        ):
            raise DomainError("Re-authenticate before approval", 403, requires_step_up=True)
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
        if set(pack.get("suitability_confirmed_plans", [])) != set(pack["selected"]) or not pack.get(
            "overall_suitability_confirmed"
        ):
            raise DomainError(
                "Confirm suitability for all three plans and the overall declaration",
                422,
                error="SUITABILITY_NOT_CONFIRMED",
            )
        dnr_snapshot = latest(db, case.id, "dnr")
        if not db.scalar(
            select(Approval).where(
                Approval.case_id == case.id,
                Approval.gate == "G0",
                Approval.payload_hash == dnr_snapshot.body_hash,
            )
        ):
            raise DomainError("The current fact-find requires broker sign-off", 422, error="DNR_NOT_APPROVED")
        if set(pack.get("dnr_sections_confirmed", [])) != {
            "priorities",
            "coverage",
            "budget",
            "household",
            "medical_flag",
        }:
            raise DomainError("Review and confirm every DNR reference section before approval", 422)
        if set(pack.get("unmet_needs_addressed", [])) != {
            f"{item['plan_id']}:{item['need']}" for item in pack["unmet_needs"]
        }:
            raise DomainError("Address every unmet need before approval", 422)
        step_up.consumed = True
        if db.scalar(
            select(Approval).where(
                Approval.case_id == case.id, Approval.gate == "G2", Approval.payload_hash == pack["pack_hash"]
            )
        ):
            raise DomainError(
                "This version already has an approval. Save a fresh review before signing again"
            )
        approval = Approval(
            case_id=case.id,
            gate="G2",
            user_id=user.id,
            payload_hash=pack["pack_hash"],
            step_up_at=session.step_up_at,
        )
        db.add(approval)
        db.flush()
        import hashlib

        audit(
            db,
            case.id,
            "G2_APPROVED",
            actor,
            {
                "broker_id": user.id,
                "approval_id": approval.id,
                "step_up_token_hash": hashlib.sha256(body["step_up_token"].encode()).hexdigest(),
                "selected_plan_ids": pack["selected"],
                "pack_hash": pack["pack_hash"],
            },
        )
        if pack.get("commission_deviation"):
            audit(db, case.id, "commission_deviation", actor, pack["commission_diagnostic"])
        if settings().core_delivery_enabled:
            db.add(
                Job(
                    case_id=case.id,
                    kind="publish",
                    due_at=utcnow().isoformat(),
                    body={"approval_id": approval.id, "pack_hash": pack["pack_hash"], "attempts": 0},
                )
            )
            audit(db, case.id, "publication_queued", actor, {"approval_id": approval.id})
        else:
            db.add(Publication(case_id=case.id, approval_id=approval.id, pack_hash=pack["pack_hash"]))
            transition(
                db,
                case,
                [State.AWAIT_APPROVAL],
                State.PUBLISHED,
                "demo_recommendation_delivered",
                actor,
                {"approval_id": approval.id, "pack_hash": pack["pack_hash"]},
            )
    else:
        raise DomainError("Unknown action", 404)
    db.flush()
    return detail(db, case)


def process_due_jobs(db, case_id=None):
    query = select(Job)
    if settings().agents_paused:
        query = query.where(Job.kind == "revoke")
    if case_id is not None:
        query = query.where(Job.case_id == case_id)
    if db.info.get("staff_user"):
        from app.case_access import visible_cases

        query = query.join(Case, Job.case_id == Case.id).where(visible_cases(db.info["staff_user"]))
    jobs = db.scalars(
        query.where(Job.status == "pending", Job.due_at <= utcnow().isoformat())
        .order_by(Job.due_at)
        .with_for_update(skip_locked=True)
    ).all()
    for job in jobs:
        case = get_case(db, job.case_id)
        if job.kind == "revoke":
            from app.publication import process_revocation

            process_revocation(db, case, job)
            continue
        if case.state in (State.PAUSED_NEEDS_HUMAN, State.COMPLAINT_FLAGGED):
            continue
        if job.kind == "publish":
            process_publication(db, case, job)
            continue
        if job.kind == "retention_review":
            audit(db, case.id, "retention_policy_review_required", "system", {"destruction_performed": False})
            job.status = "needs_human"
            continue
        if job.kind == "rerank":
            if case.state != State.BROKER_REVIEW:
                job.status = "cancelled"
                continue
            from app.shadow import rank_with_models

            transition(db, case, [case.state], State.RANKING, "reranking_started", "system")
            ranking = rank_with_models(
                db,
                {
                    "dnr": latest(db, case.id, "dnr").body,
                    "quotes": latest(db, case.id, "quotes").body["quotes"],
                    "id": uid(),
                    "case_id": case.id,
                    "tax_rate": settings().ipt_rate,
                },
            )
            save_snapshot(db, case.id, "ranking", ranking)
            target = (
                State.PAUSED_NEEDS_HUMAN
                if ranking["needs_human"] or len(ranking["top"]) < 3
                else State.BROKER_REVIEW
            )
            case.previous_state = State.BROKER_REVIEW
            transition(db, case, [case.state], target, "reranking_completed", "system")
            job.status = "completed"
            continue
        if case.state != State.QUOTES_PENDING:
            job.status = "cancelled"
            continue
        if job.kind == "chase":
            audit(db, case.id, "partner_chase", "agent:2", {"chase_number": job.body["chase_number"]})
            job.status = "completed"
            continue
        if job.kind == "rfq_timeout":
            quotes = latest(db, case.id, "quotes")
            if not quotes or sum(p["status"] == "quoted" for p in quotes.body["quotes"]) < 3:
                case.previous_state = State.QUOTES_PENDING
                transition(
                    db,
                    case,
                    [case.state],
                    State.PAUSED_NEEDS_HUMAN,
                    "insufficient_quotes",
                    "agent:2",
                    {"reason": "insufficient_quotes", "code": "H8", "phase_alias": "H3"},
                )
                job.status = "needs_human"
            else:
                job.status = "completed"
            continue
        rfq = latest(db, case.id, "rfq").body
        from app.partners import PartnerGateway
        from app.agents.quotation import RFQ

        from app.partners import active_partners
        from app.db.platform import CasePlan
        from app.agents.review import canonical_hash

        dnr_model = DNR.model_validate(latest(db, case.id, "dnr").body)
        eligible = [p for p in active_partners(db, dnr_model) if p.id in rfq["partners"]]
        if len(eligible) < settings().minimum_active_partners:
            case.previous_state = case.state
            transition(
                db,
                case,
                [case.state],
                State.PAUSED_NEEDS_HUMAN,
                "partner_panel_unavailable",
                "agent:2",
                {"reason": "insufficient_active_partners", "code": "H7"},
            )
            job.status = "needs_human"
            continue
        try:
            replies = asyncio.run(
                PartnerGateway().collect(RFQ.model_validate(rfq), job.body["scenario"], eligible)
            )
        except (DomainError, ValueError, HTTPError) as error:
            code = (
                "H8"
                if isinstance(error, HTTPError)
                else "H4"
                if isinstance(error, DomainError) and str(error).startswith("Contradictory")
                else "H7"
                if isinstance(error, DomainError) and str(error).startswith("H7:")
                else "H1"
            )
            from app.case_graph import HALTS

            case.previous_state = case.state
            transition(
                db,
                case,
                [case.state],
                State.PAUSED_NEEDS_HUMAN,
                "partner_response_rejected",
                "agent:2",
                {"code": code, "reason": HALTS[code]},
            )
            job.status = "needs_human"
            continue
        quote_snapshot = save_snapshot(db, case.id, "quotes", replies)
        for plan in replies["quotes"]:
            db.add(
                CasePlan(
                    case_id=case.id,
                    partner_id=plan["insurerId"],
                    snapshot_id=quote_snapshot.id,
                    plan_id=plan["id"],
                    revision=plan["revision"],
                    body=plan,
                    body_hash=canonical_hash(plan),
                )
            )
        special = [p for p in replies["partners"] if p["state"] in ("clarification", "referred")]
        if special:
            case.previous_state = State.QUOTES_PENDING
            transition(
                db,
                case,
                [State.QUOTES_PENDING],
                State.UW_REFERRAL if special[0]["state"] == "referred" else State.PAUSED_NEEDS_HUMAN,
                "partner_requires_human",
                "agent:2",
                {"reason": "G3" if special[0]["state"] == "referred" else "H5"},
            )
            job.status = "needs_human"
            continue
        if sum(p["status"] == "quoted" for p in replies["quotes"]) < 3:
            case.previous_state = State.QUOTES_PENDING
            transition(
                db,
                case,
                [case.state],
                State.PAUSED_NEEDS_HUMAN,
                "insufficient_quotes",
                "agent:2",
                {"reason": "insufficient_quotes", "code": "H8", "phase_alias": "H3"},
            )
            job.status = "needs_human"
            continue
        dnr = latest(db, case.id, "dnr").body
        transition(db, case, [State.QUOTES_PENDING], State.QUOTES_COLLECTED, "quotes_collected", "agent:2")
        transition(db, case, [State.QUOTES_COLLECTED], State.RANKING, "ranking_started", "system")
        from app.shadow import rank_with_models

        ranking = rank_with_models(
            db,
            {
                "dnr": dnr,
                "quotes": replies["quotes"],
                "id": uid(),
                "case_id": case.id,
                "tax_rate": settings().ipt_rate,
            },
        )
        save_snapshot(db, case.id, "ranking", ranking)
        if ranking["needs_human"] or len(ranking["top"]) < 3:
            case.previous_state = State.BROKER_REVIEW
            transition(
                db,
                case,
                [State.RANKING],
                State.PAUSED_NEEDS_HUMAN,
                "ranking_requires_human",
                "agent:3",
                {"reason": "H3" if ranking["needs_human"] else "insufficient_quotes"},
            )
        else:
            transition(db, case, [State.RANKING], State.BROKER_REVIEW, "ranking_completed", "agent:3")
        job.status = "completed"


def learning_run(db, proposer=None):
    records = []
    consumed = set()
    for proposal in db.scalars(
        select(ModelProposal).where(
            ModelProposal.status.in_(["proposed", "no_improvement", "shadow_mode", "promoted"])
        )
    ):
        consumed.update(proposal.body.get("selection_ids", []))
    # Keep the latest preference per case so repeated draft edits do not multiply the evidence.
    selections = {}
    for selection in db.scalars(
        select(Snapshot).where(Snapshot.kind == "selection").order_by(Snapshot.version)
    ):
        selections[selection.case_id] = selection
    for selection in selections.values():
        if selection.id in consumed:
            continue
        ranking = db.scalar(
            select(Snapshot)
            .where(Snapshot.case_id == selection.case_id, Snapshot.kind == "ranking")
            .order_by(Snapshot.version.desc())
        )
        if ranking and ranking.body["id"] == selection.body["ranking_id"]:
            records.append(
                {"id": selection.id, "case_id": selection.case_id, "ranking": ranking.body, **selection.body}
            )
    from app.governance import champion

    current = champion(db)
    result = invoke(
        "learning",
        {
            "records": records,
            "champion": current.weights if current.version != "user-v1" else None,
            "min_comparisons": settings().min_new_comparisons,
        },
    )
    result["champion_version"] = current.version
    result["proposed_by"] = proposer.id if proposer else None
    result["selection_ids"] = [record["id"] for record in records]
    proposal = ModelProposal(body=result, status=result["status"])
    db.add(proposal)
    db.flush()
    return {"id": proposal.id, **result}


def detail(db, case):
    data = {
        "id": case.id,
        "core_request_id": case.core_request_id,
        **case.profile,
        "state": case.state,
        "assigned_to": case.assigned_to,
        "created_at": case.created_at,
        "version": case.version,
    }
    for kind in (
        "dnr",
        "rfq",
        "quotes",
        "ranking",
        "pack",
        "publication",
        "medical_triage",
        "medical_review",
        "consumer_response",
        "consumer_link",
        "policy_bound",
        "broker_referral",
    ):
        snapshot = latest(db, case.id, kind)
        data[kind] = snapshot.body if snapshot else None
        if kind == "broker_referral" and snapshot:
            data["broker_referral_hash"] = snapshot.body_hash
    triage, review = latest(db, case.id, "medical_triage"), latest(db, case.id, "medical_review")
    if triage and review and review.created_at <= triage.created_at:
        data["medical_review"] = None
    if data.get("medical_triage", {}) is not None and not data.get("medical_triage", {}).get(
        "required", True
    ):
        data["medical_triage"] = None
    if (
        data.get("broker_referral")
        and data.get("ranking")
        and data["broker_referral"].get("ranking_id") != data["ranking"]["id"]
    ):
        data["broker_referral"] = None
    data["events"] = [
        {k: getattr(row, k) for k in ("seq", "actor", "type", "payload", "created_at", "hash")}
        for row in db.scalars(select(Activity).where(Activity.case_id == case.id).order_by(Activity.seq))
    ]
    data["delivery_pending"] = bool(
        db.scalar(select(Job).where(Job.case_id == case.id, Job.kind == "publish", Job.status == "pending"))
    )
    from app.db.platform import Complaint

    complaint = db.scalar(select(Complaint).where(Complaint.case_id == case.id))
    data["complaint"] = (
        {key: getattr(complaint, key) for key in ("id", "owner_id", "due_at", "status")}
        if complaint
        else None
    )
    return data


def evidence(db, case):
    events = db.scalars(select(Activity).where(Activity.case_id == case.id).order_by(Activity.seq)).all()
    return {
        "case": detail(db, case),
        "chain_valid": verify_chain(events),
        "approvals": [
            {k: getattr(a, k) for k in ("id", "gate", "user_id", "payload_hash", "created_at", "step_up_at")}
            for a in db.scalars(select(Approval).where(Approval.case_id == case.id))
        ],
        "snapshots": [
            {"id": s.id, "kind": s.kind, "version": s.version, "body_hash": s.body_hash, "body": s.body}
            for s in db.scalars(select(Snapshot).where(Snapshot.case_id == case.id))
        ],
    }
