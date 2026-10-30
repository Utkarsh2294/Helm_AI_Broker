"""Versioned source changes invalidate dependent drafts; withdrawals stop work."""

from typing import Literal
from pydantic import Field
from sqlalchemy import select
from app.db.models import Case, Job, utcnow
from app.db.store import latest, save_snapshot, audit
from app.schemas import Model, QuoteRequest, DomainError, State, DNR
from app.agents.review import canonical_hash


class UpdatedRequest(Model):
    id: str = Field(min_length=1, max_length=100)
    type: Literal["quote_request.updated"]
    revision: int = Field(ge=1, strict=True)
    request: QuoteRequest


class WithdrawnRequest(Model):
    id: str = Field(min_length=1, max_length=100)
    type: Literal["quote_request.withdrawn"]
    request_id: str = Field(min_length=1, max_length=100)


def handle(db, raw):
    from app import service
    from app.agents.intake import research_request
    from app.compliance.medical_ambiguity import check_medical_ambiguity
    from app.config import settings

    event = (
        UpdatedRequest.model_validate(raw)
        if raw["type"] == "quote_request.updated"
        else WithdrawnRequest.model_validate(raw)
    )
    request_id = event.request.id if isinstance(event, UpdatedRequest) else event.request_id
    case = db.scalar(select(Case).where(Case.core_request_id == request_id).with_for_update())
    if not case:
        raise DomainError("Request not found", 404)
    if isinstance(event, WithdrawnRequest):
        if case.state == State.CLOSED:
            audit(db, case.id, "request_withdrawal_repeated", "consumer")
            return case
        for job in db.scalars(select(Job).where(Job.case_id == case.id, Job.status == "pending")):
            job.status = "cancelled"
        delivered = case.state == State.PUBLISHED or (
            case.state == State.COMPLAINT_FLAGGED and case.previous_state == State.PUBLISHED
        )
        if delivered and settings().core_delivery_enabled:
            publication = latest(db, case.id, "publication")
            rec_id = publication.body.get("recommendation_id") if publication else None
            if not rec_id:
                raise DomainError("Delivered recommendation identity is missing; escalate withdrawal", 409)
            db.add(
                Job(
                    case_id=case.id,
                    kind="revoke",
                    due_at=utcnow().isoformat(),
                    body={"recommendation_id": rec_id, "attempts": 0},
                )
            )
        save_snapshot(db, case.id, "core_withdrawal", {"event_id": event.id, "at": utcnow().isoformat()})
        if case.state == State.COMPLAINT_FLAGGED:
            case.previous_state = State.CLOSED
            audit(db, case.id, "request_withdrawn_during_complaint", "consumer")
        else:
            service.transition(db, case, [case.state], State.CLOSED, "core_request_withdrawn", "consumer")
        return case
    if case.state in {State.PUBLISHED, State.CLOSED, State.COMPLAINT_FLAGGED}:
        raise DomainError(
            "Published, closed or complaint-held requests need human review before source changes", 409
        )
    previous = latest(db, case.id, "core_revision")
    digest = canonical_hash(event.request.model_dump(mode="json"))
    if previous and event.revision <= previous.body["revision"]:
        if event.revision == previous.body["revision"] and digest != previous.body["request_hash"]:
            raise DomainError("Contradictory source revision", 409)
        audit(db, case.id, "obsolete_request_revision_ignored", "consumer", {"revision": event.revision})
        return case
    for job in db.scalars(
        select(Job).where(Job.case_id == case.id, Job.status.in_(["pending", "needs_human"]))
    ):
        job.status = "cancelled"
    old = latest(db, case.id, "dnr")
    service.transition(
        db,
        case,
        [case.state],
        State.INTAKE_RUNNING,
        "consumer_requirements_updated",
        "consumer",
        {"revision": event.revision},
    )
    triage = check_medical_ambiguity(event.request.model_dump())
    dnr = (
        research_request(event.request)
        if triage
        else DNR.model_validate(service.invoke("intake", event.request.model_dump()))
    )
    dnr.version = old.version + 1 if old else 1
    for key, fact in dnr.facts.items():
        fact.source = f"core_event:{event.id}#{key}"
    save_snapshot(db, case.id, "request", event.request.model_dump(mode="json"))
    save_snapshot(db, case.id, "dnr", dnr.model_dump(mode="json"))
    save_snapshot(
        db,
        case.id,
        "core_revision",
        {"revision": event.revision, "request_hash": digest, "event_id": event.id},
    )
    save_snapshot(
        db,
        case.id,
        "medical_triage",
        {"required": bool(triage), **(triage or {}), "source_revision": event.revision},
    )
    case.profile = {
        **case.profile,
        "name": event.request.name,
        "cover_type": event.request.cover_type,
        "postcode_district": event.request.postcode_district,
    }
    target = (
        State.PAUSED_NEEDS_HUMAN
        if triage or dnr.vulnerability_flags
        else State.NEEDS_INFO
        if dnr.missing
        else State.FACTFIND_REVIEW
    )
    case.previous_state = State.FACTFIND_REVIEW
    service.transition(
        db,
        case,
        [State.INTAKE_RUNNING],
        target,
        "intake_completed",
        "agent:1",
        {"source_revision": event.revision},
    )
    return case
