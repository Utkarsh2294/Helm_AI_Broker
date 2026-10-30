"""Single-firm staff access: assigned cases are private to their broker and reviewers."""

from sqlalchemy import or_
from app.db.models import Case
from app.schemas import DomainError


def sees_all(user):
    return user.role in ("compliance_officer", "auditor", "admin", "lead_broker", "senior_broker") or getattr(
        user, "is_lead_broker", False
    )


def visible_cases(user):
    return True if sees_all(user) else or_(Case.assigned_to == user.id, Case.assigned_to.is_(None))


def require_case_access(case, user):
    if not sees_all(user) and case.assigned_to and case.assigned_to != user.id:
        raise DomainError("Case not found", 404)
