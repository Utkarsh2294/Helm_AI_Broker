"""Session authentication shared by the broker API and MFA routes."""

import hashlib
import secrets
from datetime import datetime, timedelta
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Request
from sqlalchemy import select
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
    from app.auth.account_lock import lock_state, record_failure, clear_failures

    state = lock_state(db, email)
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    # Equal-cost verification for unknown users avoids an obvious timing oracle.
    encoded = user.password_hash if user else DUMMY_HASH
    if not verify_password(password, encoded) or not user:
        record_failure(db, state, user)
    if not user.is_active:
        raise DomainError("This staff account is disabled", 403)
    clear_failures(state, user)
    return user


DUMMY_HASH = hasher.hash(secrets.token_urlsafe(24))


def new_session(db, user):
    from app.auth.tokens import mint_token

    if user.is_active is False:
        raise DomainError("This staff account is disabled", 403)
    token = mint_token(user.id, role=user.role)
    row = LoginSession(
        id=digest(token),
        user_id=user.id,
        csrf=secrets.token_urlsafe(32),
        expires_at=(utcnow() + timedelta(minutes=15)).isoformat(),
    )
    db.add(row)
    return row, token


def identity(db, request: Request):
    token = request.cookies.get("helm_session", "")
    claims = None
    if "." in token:
        from app.auth.tokens import verify_token

        claims = verify_token(token)
    pair = (
        db.execute(
            select(LoginSession, User)
            .join(User, User.id == LoginSession.user_id)
            .where(LoginSession.id == digest(token))
        ).first()
        if token
        else None
    )
    row, user = pair if pair else (None, None)
    if not row or datetime.fromisoformat(row.expires_at) <= utcnow():
        raise DomainError("Sign in to continue", 401)
    if not user or not user.is_active or (claims and claims["sub"] != str(user.id)):
        raise DomainError("Sign in to continue", 401)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        csrf = request.headers.get("X-CSRF-Token", "")
        if not secrets.compare_digest(row.csrf, csrf):
            raise DomainError("Invalid session verification token", 403)
    db.info["staff_user"] = user
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
