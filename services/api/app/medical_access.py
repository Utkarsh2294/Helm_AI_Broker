from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request
from app.auth import identity
from app.auth.mfa import load_challenge
from app.compliance.medical_firewall import MEDICAL_ROLES
from app.db.models import utcnow
from app.db.platform import MedicalAccess
from app.db.store import latest, audit
from app.main import database
from app.schemas import DomainError
from app import service

router = APIRouter(prefix="/api/v1/cases")


def medical_permission(db, case, user):
    dnr = latest(db, case.id, "dnr")
    if user.role not in MEDICAL_ROLES or not dnr or not dnr.body.get("consent_to_share"):
        raise DomainError("Current medical consent and an authorised role are required", 403)


def require_medical_access(db, case, user, session):
    medical_permission(db, case, user)
    grant = db.get(MedicalAccess, (session.id, case.id))
    if not grant or grant.user_id != user.id or datetime.fromisoformat(grant.expires_at) <= utcnow():
        raise DomainError(
            "Re-authenticate to reveal medical statements for this case", 403, requires_step_up=True
        )


@router.post("/{case_id}/medical-access")
def grant_access(case_id: str, request: Request, db=Depends(database, scope="function")):
    user, session = identity(db, request)
    case = service.get_case(db, case_id)
    medical_permission(db, case, user)
    if not session.step_up_at or utcnow() - datetime.fromisoformat(session.step_up_at) > timedelta(minutes=5):
        raise DomainError("Fresh verification is required", 403, requires_step_up=True)
    try:
        proof = load_challenge(db, request.headers.get("X-Step-Up", ""), "step-up")
    except DomainError:
        raise DomainError("Fresh verification is required", 403, requires_step_up=True)
    if proof.user_id != user.id or proof.body.get("session_id") != session.id:
        raise DomainError("Verification belongs to a different session", 403)
    proof.consumed = True
    grant = db.get(MedicalAccess, (session.id, case.id))
    if grant is None:
        grant = MedicalAccess(session_id=session.id, case_id=case.id, user_id=user.id)
        db.add(grant)
    grant.expires_at = (utcnow() + timedelta(hours=1)).isoformat()
    audit(db, case.id, "medical_access_granted", f"broker:{user.id}", {"expires_at": grant.expires_at})
    return {"granted": True, "expires_at": grant.expires_at}
