"""Recall-first human triage; opening a complaint never sends a response."""

from datetime import timedelta
from sqlalchemy import select
from app.clock import get_clock
from app.db.models import User, utcnow
from app.db.platform import Complaint
from app.db.store import save_snapshot, audit
from app.schemas import DomainError, State


def open_complaint(db, case, actor, reason):
    from app.service import transition

    if case.state == State.COMPLAINT_FLAGGED:
        save_snapshot(
            db, case.id, "complaint_message", {"reason": reason, "actor": actor, "at": utcnow().isoformat()}
        )
        audit(db, case.id, "complaint_message_received", actor)
        return
    if case.state == State.CLOSED:
        raise DomainError("Closed-case complaints require a separate compliance review", 409)
    owner = db.scalar(select(User).where(User.role == "compliance_officer", User.is_active.is_(True)))
    if not owner:
        raise DomainError("Designate an active compliance owner before opening a complaint", 409)
    complaint = db.scalar(select(Complaint).where(Complaint.case_id == case.id).with_for_update())
    due_at = utcnow() + get_clock().wall_delay(timedelta(days=56))
    if complaint:
        complaint.status, complaint.due_at, complaint.owner_id, complaint.resolution = (
            "open",
            due_at,
            owner.id,
            None,
        )
    else:
        db.add(Complaint(case_id=case.id, owner_id=owner.id, due_at=due_at))
    case.previous_state = case.state
    save_snapshot(
        db,
        case.id,
        "complaint_received",
        {
            "reason": reason,
            "owner_id": owner.id,
            "by": actor,
            "at": utcnow().isoformat(),
            "business_deadline_days": 56,
        },
    )
    transition(db, case, [case.state], State.COMPLAINT_FLAGGED, "complaint_flagged", actor)
