"""Fictional, durable two-decision journey. Automated preparation is never human approval."""

from datetime import timedelta
from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy import select
from app import service
from app.auth import identity
from app.agents.review import canonical_hash
from app.config import settings
from app.db.models import Job, uid, utcnow
from app.db.store import latest, save_snapshot, audit
from app.demo_documents import database, demo_only
from app.schemas import DNR, DomainError, Model, QuoteRequest, State

router = APIRouter(prefix="/api/v1")
FLOW = "fictional-two-decisions-v1"
FINAL_DECLARATION = (
    "I have reviewed the client facts, budget, priorities, coverage, household and medical declaration; "
    "the three policies in my chosen order; the suitability statement, every listed gap, terms and "
    "disclosures. I confirm suitability and accept responsibility for this fictional recommendation."
)


def is_agentic_demo(db, case):
    if (
        settings().clock_mode != "demo"
        or settings().partner_mode not in {"simulator", "http_simulator"}
        or not case.core_request_id.startswith("agentic-demo-")
        or case.profile.get("workflow") != FLOW
    ):
        return False
    marker = latest(db, case.id, "demo_workflow")
    source = latest(db, case.id, "request")
    return bool(marker and source and marker.body.get("source_hash") == source.body_hash)


def require_preparation(db, case):
    if not is_agentic_demo(db, case):
        raise DomainError("Automatic preparation is limited to the generated fictional demo", 403)
    dnr = latest(db, case.id, "dnr")
    prepared = latest(db, case.id, "demo_preparation")
    if not dnr or not prepared or prepared.body["dnr_hash"] != dnr.body_hash:
        raise DomainError("Demo facts changed; automatic preparation is no longer valid", 409)
    model = DNR.model_validate(dnr.body)
    if model.missing or not model.consent_to_share or model.medical_items or model.vulnerability_flags:
        raise DomainError("This case needs human clarification before quotations", 409)
    return model


def enqueue(db, case_id, kind, body=None):
    db.add(
        Job(case_id=case_id, kind=kind, due_at=(utcnow() + timedelta(seconds=1)).isoformat(), body=body or {})
    )


def poll_agentic(session_factory):
    """Local preview runner; Compose uses the existing durable Arq worker instead."""
    with session_factory() as db:
        ids = db.scalars(
            select(Job.case_id).where(Job.status == "pending", Job.due_at <= utcnow().isoformat()).distinct()
        ).all()
        for case_id in ids:
            if not case_id:
                continue
            case = service.get_case(db, case_id)
            if is_agentic_demo(db, case):
                service.process_due_jobs(db, case_id)
        db.commit()


@router.post("/demo/journeys")
def start_demo(request: Request, db=Depends(database, scope="function")):
    demo_only()
    user, _ = identity(db, request)
    service.require_broker(user)
    if settings().partner_mode not in {"simulator", "http_simulator"}:
        raise DomainError("The automatic demo requires fictional partners", 403)
    # Fixed safe fixture: this endpoint accepts no customer payload or override flags.
    source = QuoteRequest.model_validate(
        {
            "id": "agentic-demo-" + uid(),
            "name": "Morgan Demo",
            "postcode_district": "M20",
            "needs": {
                "budget_annual_pence": 180000,
                "coverage": {"cancer": {"level": 3, "must_have": True}, "outpatient": {"level": 3}},
            },
        }
    )
    case = service.import_request(db, source, defer_intake=True)
    case.profile = {**case.profile, "workflow": FLOW}
    case.assigned_to = user.id
    save_snapshot(
        db,
        case.id,
        "demo_workflow",
        {
            "flow": FLOW,
            "fictional": True,
            "source_hash": latest(db, case.id, "request").body_hash,
            "started_by": user.id,
            "human_decisions": ["policy_selection_and_order", "final_signoff"],
            "automatic_preparation_is_human_approval": False,
        },
    )
    audit(db, case.id, "demo_automation_started", "demo-automation", {"flow": FLOW})
    enqueue(db, case.id, "demo_intake")
    return service.detail(db, case)


class Selection(Model):
    ranking_id: str = Field(min_length=1, max_length=100)
    selected: list[str] = Field(min_length=3, max_length=3)
    confirm_selection: bool = False


@router.post("/demo/journeys/{case_id}/selection")
def select_policies(case_id: str, body: Selection, request: Request, db=Depends(database, scope="function")):
    user, _ = identity(db, request)
    service.require_broker(user)
    case = service.get_case(db, case_id)
    require_preparation(db, case)
    ranking = latest(db, case.id, "ranking")
    if case.state != State.BROKER_REVIEW or not ranking or ranking.body["id"] != body.ranking_id:
        raise DomainError("This ranking is no longer ready; refresh the case", 409)
    available = {row["plan"]["id"] for row in ranking.body["top"]}
    if not body.confirm_selection or len(set(body.selected)) != 3 or set(body.selected) - available:
        raise DomainError("Choose and confirm three distinct current policies in your preferred order", 422)
    selection = save_snapshot(
        db,
        case.id,
        "selection",
        {
            "selected": body.selected,
            "ranking_id": body.ranking_id,
            "by": user.id,
            "source": "broker_policy_selection_and_order",
            "survey": {"thumbs": {}},
            "star_ratings_collected": False,
            "gaps_reviewed_at_selection": True,
            "dnr_hash": latest(db, case.id, "dnr").body_hash,
        },
    )
    service.transition(
        db,
        case,
        [State.BROKER_REVIEW],
        State.SUITABILITY_DRAFT,
        "review_started",
        f"broker:{user.id}",
        {
            "decision": 1,
            "selection_hash": selection.body_hash,
            "selected_plan_ids": body.selected,
        },
    )
    enqueue(db, case.id, "demo_pack", {"selection_hash": selection.body_hash})
    return service.detail(db, case)


def validate_selection(db, case, user, pack):
    require_preparation(db, case)
    selection = latest(db, case.id, "selection")
    ranking = latest(db, case.id, "ranking")
    if (
        not selection
        or not ranking
        or selection.body.get("by") != user.id
        or selection.body.get("ranking_id") != ranking.body["id"]
        or pack.get("ranking_id") != ranking.body["id"]
        or selection.body.get("selected") != pack.get("selected")
        or selection.body.get("dnr_hash") != latest(db, case.id, "dnr").body_hash
        or pack.get("selection_hash") != selection.body_hash
    ):
        raise DomainError(
            "The signed selection, case facts or ranking changed; rebuild the recommendation", 409
        )


class FinalSignoff(Model):
    pack_hash: str = Field(min_length=64, max_length=64)
    step_up_token: str = Field(min_length=1, max_length=8192)
    confirm_final_review: bool = False


@router.post("/demo/journeys/{case_id}/signoff")
def signoff(case_id: str, body: FinalSignoff, request: Request, db=Depends(database, scope="function")):
    user, session = identity(db, request)
    service.require_broker(user)
    case = service.get_case(db, case_id)
    require_preparation(db, case)
    snapshot = latest(db, case.id, "pack")
    if case.state != State.AWAIT_APPROVAL or not snapshot or snapshot.body["pack_hash"] != body.pack_hash:
        raise DomainError("The recommendation changed; review the latest version", 409)
    if not body.confirm_final_review:
        raise DomainError("Final approval requires your explicit review declaration", 422)
    pack = {key: value for key, value in snapshot.body.items() if key != "pack_hash"}
    validate_selection(db, case, user, pack)
    # These acknowledgements arise together from the explicit, authenticated signature,
    # never from an agent, a page load, a saved selection or a pre-ticked control.
    pack.update(
        {
            "reviewed_pack_hash": body.pack_hash,
            "final_review_declaration": FINAL_DECLARATION,
            "final_review_by": user.id,
            "review_saved_at": utcnow().isoformat(),
            "dnr_sections_confirmed": ["priorities", "coverage", "budget", "household", "medical_flag"],
            "suitability_confirmed_plans": pack["selected"],
            "overall_suitability_confirmed": True,
            "unmet_needs_addressed": [f"{item['plan_id']}:{item['need']}" for item in pack["unmet_needs"]],
        }
    )
    pack["pack_hash"] = canonical_hash(pack)
    save_snapshot(db, case.id, "pack", pack)
    result = service.act(
        db,
        case.id,
        "approve",
        user,
        session,
        {
            "pack_hash": pack["pack_hash"],
            "step_up_token": body.step_up_token,
        },
    )
    audit(
        db,
        case.id,
        "demo_final_review_signed",
        f"broker:{user.id}",
        {
            "decision": 2,
            "reviewed_pack_hash": body.pack_hash,
            "signed_pack_hash": pack["pack_hash"],
        },
    )
    enqueue(db, case.id, "demo_learning")
    return result


def process_job(db, case, job):
    if not is_agentic_demo(db, case):
        job.status = "cancelled"
        return
    if case.state in {State.CLOSED, State.COMPLAINT_FLAGGED, State.PAUSED_NEEDS_HUMAN, State.UW_REFERRAL}:
        # A hold stays a hold. The existing controls can resolve the exception explicitly.
        return
    if job.kind == "demo_intake" and case.state == State.INTAKE_RUNNING:
        service.finish_intake(db, case, QuoteRequest.model_validate(latest(db, case.id, "request").body))
        if case.state == State.FACTFIND_REVIEW:
            enqueue(db, case.id, "demo_prepare")
    elif job.kind == "demo_prepare" and case.state == State.FACTFIND_REVIEW:
        from app.agents.quotation import build_rfq
        from app.partners import active_partners

        dnr = latest(db, case.id, "dnr")
        model = DNR.model_validate(dnr.body)
        partners = active_partners(db, model)
        if len(partners) < settings().minimum_active_partners:
            job.status = "needs_human"
            case.previous_state = case.state
            service.transition(
                db,
                case,
                [case.state],
                State.PAUSED_NEEDS_HUMAN,
                "demo_automation_held",
                "demo-automation",
                {"reason": "insufficient_active_partners", "code": "H7"},
            )
            return
        save_snapshot(
            db,
            case.id,
            "demo_preparation",
            {"dnr_hash": dnr.body_hash, "fictional": True, "human_approved": False},
        )
        require_preparation(db, case)
        rfq = build_rfq(model, signed_off=False, demo_preparation=True, partner_ids=[p.id for p in partners])
        save_snapshot(db, case.id, "rfq", rfq.model_dump(mode="json"))
        service.transition(
            db,
            case,
            [State.FACTFIND_REVIEW],
            State.QUOTES_PENDING,
            "demo_quotation_started",
            "demo-automation",
            {
                "why": "Complete fictional facts and consent permit simulator-only preparation; no human release recorded.",
            },
        )
        enqueue(db, case.id, "collect_quotes", {"scenario": "happy"})
    elif job.kind == "demo_rank" and case.state == State.RANKING:
        from app.shadow import rank_with_models

        require_preparation(db, case)
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
        halted = ranking["needs_human"] or len(ranking["top"]) < 3
        if halted:
            case.previous_state = State.BROKER_REVIEW
        service.transition(
            db,
            case,
            [State.RANKING],
            State.PAUSED_NEEDS_HUMAN if halted else State.BROKER_REVIEW,
            "ranking_requires_human" if halted else "ranking_completed",
            "agent:3",
        )
    elif job.kind == "demo_pack" and case.state == State.SUITABILITY_DRAFT:
        require_preparation(db, case)
        selection = latest(db, case.id, "selection")
        if selection.body_hash != job.body["selection_hash"]:
            raise DomainError("Selection changed during recommendation preparation", 409)
        pack = service.invoke(
            "review",
            {
                "dnr": latest(db, case.id, "dnr").body,
                "ranking": latest(db, case.id, "ranking").body,
                "selected": selection.body["selected"],
                "survey": {"thumbs": {}},
                "acknowledgements": selection.body["selected"],
                "two_touchpoint_demo": True,
            },
        )
        pack = {key: value for key, value in pack.items() if key != "pack_hash"}
        pack.update({"selection_hash": selection.body_hash, "workflow": FLOW, "feedback_collected": False})
        pack["pack_hash"] = canonical_hash(pack)
        save_snapshot(db, case.id, "pack", pack)
        service.transition(
            db, case, [State.SUITABILITY_DRAFT], State.AWAIT_APPROVAL, "pack_drafted", "agent:4"
        )
    elif job.kind == "demo_learning":
        if case.state != State.PUBLISHED:
            job.due_at = (utcnow() + timedelta(seconds=3)).isoformat()
            return
        result = service.learning_run(db)
        save_snapshot(db, case.id, "demo_learning", result)
        audit(
            db,
            case.id,
            "learning_evaluated",
            "agent:5",
            {
                "status": result["status"],
                "comparison_count": result["comparison_count"],
                "auto_applied": False,
            },
        )
    else:
        job.status = "cancelled"
        return
    job.status = "completed"
