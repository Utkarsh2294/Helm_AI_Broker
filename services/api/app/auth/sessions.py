import secrets
from datetime import datetime, timedelta
from sqlalchemy import select
from app.auth import digest, hasher, new_session, public_user, verify_password
from app.config import settings
from app.db.models import LoginSession, User, uid, utcnow
from app.db.platform import RefreshToken, SessionDevice
from app.schemas import DomainError


def issue(db, user, request, response, family_id=None):
    row, access = new_session(db, user)
    row.expires_at = (utcnow() + timedelta(minutes=15)).isoformat()
    refresh = secrets.token_urlsafe(32)
    db.add(
        RefreshToken(
            id=digest(refresh),
            family_id=family_id or uid(),
            user_id=user.id,
            session_id=row.id,
            password_hash=hasher.hash(refresh),
            expires_at=(utcnow() + timedelta(hours=settings().session_hours)).isoformat(),
        )
    )
    db.add(
        SessionDevice(
            session_id=row.id,
            user_id=user.id,
            ip=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", "unknown")[:300],
        )
    )
    options = {"secure": settings().cookie_secure, "samesite": "strict", "path": "/"}
    response.set_cookie("helm_session", access, httponly=True, max_age=900, **options)
    response.set_cookie(
        "helm_refresh", refresh, httponly=True, max_age=settings().session_hours * 3600, **options
    )
    response.set_cookie(
        "helm_csrf", row.csrf, httponly=False, max_age=settings().session_hours * 3600, **options
    )
    return {"user": public_user(user), "csrf": row.csrf, "session_id": row.id}


def revoke_family(db, family_id):
    for token in db.scalars(select(RefreshToken).where(RefreshToken.family_id == family_id)):
        token.revoked = True
        session = db.get(LoginSession, token.session_id)
        if session:
            db.delete(session)


def rotate(db, raw, request, response):
    old = db.scalar(select(RefreshToken).where(RefreshToken.id == digest(raw)).with_for_update())
    if not old or not verify_password(raw, old.password_hash):
        raise DomainError("Invalid refresh token", 401)
    if old.revoked:
        revoke_family(db, old.family_id)
        db.commit()  # security revocation must survive the error response
        raise DomainError("Refresh reuse detected; session family revoked", 401)
    if datetime.fromisoformat(old.expires_at) <= utcnow():
        raise DomainError("Refresh session expired", 401)
    old.revoked = True
    previous = db.get(LoginSession, old.session_id)
    if previous:
        db.delete(previous)
    return issue(db, db.get(User, old.user_id), request, response, old.family_id)
