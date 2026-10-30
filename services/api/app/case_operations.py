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


class CloseWithoutAdvice(Model):
    ranking_id: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=20, max_length=2000)
    confirmed: bool = False


@router.post("/cases/{case_id}/close-without-advice")
def close_without_advice(
    case_id: str, body: CloseWithoutAdvice, request: Request, db=Depends(database, scope="function")
):
    from app.db.store import latest, save_snapshot
    from app.plan_ratings import validate_reviews, reviews_hash

    user, _ = identity(db, request)
    service.require_broker(user)
    case = service.get_case(db, case_id)
    if case.state != State.BROKER_REVIEW:
        raise DomainError("Only an open comparison can be closed without advice", 409)
    ranking = latest(db, case_id, "ranking")
    if not ranking or body.ranking_id != ranking.body["id"]:
        raise DomainError("Ranking changed. Review the current comparison.", 409)
    reviews = validate_reviews(db, case_id, ranking.body, user)
    if not reviews or any(row.decision != "NO" for row in reviews):
        raise DomainError("Exclude every shortlisted plan before closing without advice", 422)
    if not body.confirmed or len(body.reason.strip()) < 20:
        raise DomainError("Confirm closure and record a reason in at least 20 characters", 422)
    save_snapshot(
        db,
        case_id,
        "no_advice_closure",
        {
            "ranking_id": body.ranking_id,
            "reason": body.reason.strip(),
            "by": user.id,
            "ratings_hash": reviews_hash(reviews),
            "at": utcnow().isoformat(),
            "recommendation_sent": False,
        },
    )
    for job in db.scalars(select(Job).where(Job.case_id == case_id, Job.status == "pending")):
        job.status = "cancelled"
    service.transition(
        db, case, [State.BROKER_REVIEW], State.CLOSED, "no_suitable_plans", f"broker:{user.id}"
    )
    return {"state": case.state, "recommendation_sent": False}


@router.get("/cases/{case_id}/closure.pdf")
def closure(case_id: str, request: Request, db=Depends(database, scope="function")):
    import base64
    from fastapi.responses import Response
    from app.db.store import latest

    identity(db, request)
    service.get_case(db, case_id)
    record = latest(db, case_id, "closure_pdf")
    if not record:
        raise DomainError("No closure record is available", 404)
    return Response(
        base64.b64decode(record.body["base64"]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="helm-closure-{case_id}.pdf"'},
    )


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
    if len(body.resolution.strip()) < 20:
        raise DomainError("Record the complaint resolution in at least 20 characters", 422)
    if not complaint or case.state != State.COMPLAINT_FLAGGED:
        raise DomainError("No open complaint")
    if user.role != "compliance_officer" or complaint.owner_id != user.id:
        raise DomainError("Only the designated compliance owner can close this complaint", 403)
    complaint.status, complaint.resolution = (
        "closed",
        {"text": body.resolution, "by": user.id, "at": utcnow().isoformat()},
    )
    from app.db.store import save_snapshot

    save_snapshot(db, case_id, "complaint_resolution", complaint.resolution)
    service.transition(
        db,
        case,
        [State.COMPLAINT_FLAGGED],
        case.previous_state,
        "complaint_resolved",
        f"compliance:{user.id}",
    )
    return {"state": case.state, "complaint_status": "closed"}
