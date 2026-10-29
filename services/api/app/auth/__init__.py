"""Session authentication shared by the broker API and MFA routes."""

import hashlib
import secrets
from datetime import datetime, timedelta
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Request
from sqlalchemy import select
from app.config import settings
from app.db.models import LoginSession, User, utcnow
from app.schemas import DomainError

hasher = PasswordHasher()


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def verify_password(password, encoded):
    try:
        return hasher.verify(encoded, password)
    except VerificationError:
        return False


def authenticate(db, email, password):
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    # Equal-cost verification for unknown users avoids an obvious timing oracle.
    encoded = user.password_hash if user else DUMMY_HASH
    if not verify_password(password, encoded) or not user:
        raise DomainError("Email or password is incorrect", 401)
    return user


DUMMY_HASH = hasher.hash(secrets.token_urlsafe(24))


def new_session(db, user):
    token = secrets.token_urlsafe(32)
    row = LoginSession(
        id=digest(token),
        user_id=user.id,
        csrf=secrets.token_urlsafe(32),
        expires_at=(utcnow() + timedelta(hours=settings().session_hours)).isoformat(),
    )
    db.add(row)
    return row, token


def identity(db, request: Request):
    token = request.cookies.get("helm_session", "")
    row = db.get(LoginSession, digest(token)) if token else None
    if not row or datetime.fromisoformat(row.expires_at) <= utcnow():
        raise DomainError("Sign in to continue", 401)
    user = db.get(User, row.user_id)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        csrf = request.headers.get("X-CSRF-Token", "")
        if not secrets.compare_digest(row.csrf, csrf):
            raise DomainError("Invalid session verification token", 403)
    return user, row


def public_user(user):
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "can_approve": user.can_approve,
        "is_lead_broker": user.is_lead_broker,
        "fca_irn": user.fca_irn,
    }
