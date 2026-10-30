from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy import select
from app.auth import identity
from app.main import database
from app.db.models import Job, utcnow
from app.db.platform import Complaint
from app.db.store import audit
from app.schemas import DomainError, State, Model
from app import service

router = APIRouter(prefix="/api/v1")


@router.post("/cases/{case_id}/ranking", status_code=202)
def enqueue_ranking(case_id: str, request: Request, db=Depends(database, scope="function")):
    user, _ = identity(db, request)
    service.require_broker(user)
    case = service.get_case(db, case_id)
    if case.state != State.BROKER_REVIEW:
        raise DomainError("Only a comparison awaiting broker review can be ranked again")
    existing = db.scalar(
        select(Job).where(Job.case_id == case_id, Job.kind == "rerank", Job.status == "pending")
    )
    if not existing:
        existing = Job(case_id=case_id, kind="rerank", due_at=utcnow().isoformat(), body={})
        db.add(existing)
        db.flush()
        audit(db, case_id, "ranking_queued", f"broker:{user.id}")
    return {"job_id": existing.id, "status": "queued"}


class ComplaintResolution(Model):
    resolution: str = Field(min_length=20, max_length=3000)


class MedicalReview(Model):
    decision: str = Field(pattern="^(record_declared|no_ambiguity|seek_clarification)$")
    reason: str = Field(min_length=30, max_length=3000)


@router.post("/cases/{case_id}/medical-review")
def review_medical_wording(
    case_id: str, body: MedicalReview, request: Request, db=Depends(database, scope="function")
):
    from app.compliance.medical_ambiguity import pending_review
    from app.medical_access import require_medical_access
    from app.db.store import save_snapshot

    user, session = identity(db, request)
    if len(body.reason.strip()) < 30:
        raise DomainError("Explain the review in at least 30 characters", 422)
    service.require_broker(user)
    case = service.get_case(db, case_id)
    if case.state not in (
        State.PAUSED_NEEDS_HUMAN,
        State.NEEDS_INFO,
        State.FACTFIND_REVIEW,
    ) or not pending_review(db, case_id):
        raise DomainError("No medical wording review is pending", 409)
    require_medical_access(db, case, user, session)
    resolved = body.decision != "seek_clarification"
    save_snapshot(
        db,
        case_id,
        "medical_review",
        {**body.model_dump(), "resolved": resolved, "by": user.id, "at": utcnow().isoformat()},
    )
    audit(
        db,
        case_id,
        "medical_wording_reviewed",
        f"broker:{user.id}",
        {"decision": body.decision, "resolved": resolved},
    )
    service.transition(
        db,
        case,
        [case.state],
        State.FACTFIND_REVIEW if resolved else State.NEEDS_INFO,
        "medical_review_recorded",
        f"broker:{user.id}",
    )
    from app.compliance.medical_firewall import safe_case

    return safe_case(service.detail(db, case), user)


@router.post("/cases/{case_id}/complaints/resolve")
def resolve_complaint(
    case_id: str, body: ComplaintResolution, request: Request, db=Depends(database, scope="function")
):
    user, _ = identity(db, request)
    case = service.get_case(db, case_id)
    complaint = db.scalar(select(Complaint).where(Complaint.case_id == case_id).with_for_update())
    if not complaint or case.state != State.COMPLAINT_FLAGGED:
        raise DomainError("No open complaint")
    if user.role != "compliance_officer" or complaint.owner_id != user.id:
        raise DomainError("Only the designated compliance owner can close this complaint", 403)
    complaint.status, complaint.resolution = (
        "closed",
        {"text": body.resolution, "by": user.id, "at": utcnow().isoformat()},
    )
    service.transition(
        db,
        case,
        [State.COMPLAINT_FLAGGED],
        case.previous_state,
        "complaint_resolved",
        f"compliance:{user.id}",
    )
    return {"state": case.state, "complaint_status": "closed"}
