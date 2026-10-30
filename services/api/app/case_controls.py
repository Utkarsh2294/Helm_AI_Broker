"""Reasoned assignment and priority changes never approve or resume advice."""

from typing import Literal
from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy import select
from app.auth import identity
from app.main import database
from app import service
from app.db.models import User
from app.db.store import audit, save_snapshot
from app.agents.review import canonical_hash
from app.schemas import Model, DomainError, State

router = APIRouter(prefix="/api/v1")


def lead(user):
    return user.role == "lead_broker" or user.is_lead_broker


class Control(Model):
    operation: Literal["assign", "priority", "takeover"]
    expected_version: int = Field(ge=1, strict=True)
    reason: str = Field(min_length=20, max_length=2000)
    assignee_id: str | None = None
    priority: Literal["normal", "urgent"] | None = None


@router.get("/case-controls/assignees")
def assignees(request: Request, db=Depends(database, scope="function")):
    user, _ = identity(db, request)
    service.require_broker(user)
    if not lead(user):
        return [{"id": user.id, "name": user.name}]
    return [
        {"id": row.id, "name": row.name}
        for row in db.scalars(
            select(User)
            .where(User.is_active.is_(True), User.role.in_(["authorised_broker", "lead_broker"]))
            .order_by(User.name)
        )
    ]


@router.post("/cases/{case_id}/controls")
def control(case_id: str, body: Control, request: Request, db=Depends(database, scope="function")):
    user, _ = identity(db, request)
    service.require_broker(user)
    case = service.get_case(db, case_id)
    if case.version != body.expected_version:
        raise DomainError("Case changed. Refresh before changing its controls.", 409)
    if case.state == State.CLOSED:
        raise DomainError("Closed case controls are read-only", 409)
    if len(body.reason.strip()) < 20:
        raise DomainError("Explain this change in at least 20 characters", 422)
    before = {"assigned_to": case.assigned_to, "priority": case.priority}
    if body.operation == "priority":
        if body.priority is None:
            raise DomainError("Choose a priority", 422)
        case.priority = body.priority
    else:
        target = user.id if body.operation == "takeover" else body.assignee_id
        if not target or (not lead(user) and (target != user.id or case.assigned_to not in (None, user.id))):
            raise DomainError("Only the lead broker can reassign a colleague's case", 403)
        assignee = db.get(User, target)
        if (
            not assignee
            or not assignee.is_active
            or assignee.role not in ("authorised_broker", "lead_broker")
        ):
            raise DomainError("Choose an active broker", 422)
        if body.operation == "takeover" and case.state != State.PAUSED_NEEDS_HUMAN:
            raise DomainError("Takeover requires a paused case", 409)
        case.assigned_to = target
    after = {"assigned_to": case.assigned_to, "priority": case.priority}
    if before == after:
        raise DomainError("Choose a change before saving", 422)
    save_snapshot(
        db,
        case.id,
        "case_control",
        {
            "operation": body.operation,
            "reason": body.reason.strip(),
            "by": user.id,
            "before": before,
            "after": after,
        },
    )
    audit(
        db,
        case.id,
        "case_control_changed",
        f"broker:{user.id}",
        {
            "operation": body.operation,
            "before": before,
            "after": after,
            "reason_hash": canonical_hash(body.reason.strip()),
        },
    )
    db.flush()
    return {"version": case.version, "state": case.state, **after}
