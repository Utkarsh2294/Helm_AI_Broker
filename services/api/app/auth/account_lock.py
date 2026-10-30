"""Per-identity failed-login locks, including unknown identities to avoid enumeration."""

import hashlib
import hmac
from datetime import datetime, timedelta
from sqlalchemy import select
from app.config import settings
from app.db.models import stamp, utcnow
from app.db.platform import LoginAttempt
from app.schemas import DomainError


def identity_key(email):
    return hmac.new(
        settings().secret_key.encode(), email.strip().lower().encode(), hashlib.sha256
    ).hexdigest()


def ensure_not_locked(db, email):
    state = db.get(LoginAttempt, identity_key(email))
    if state and state.locked_until and datetime.fromisoformat(state.locked_until) > utcnow():
        raise DomainError(
            "Account temporarily locked. Try again after 15 minutes or contact your administrator.", 423
        )


def lock_state(db, email):
    from sqlalchemy.dialects.postgresql import insert as postgres_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    key = identity_key(email)
    insert = postgres_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    db.execute(
        insert(LoginAttempt)
        .values(identity_hash=key, failures=0, updated_at=stamp())
        .on_conflict_do_nothing(index_elements=["identity_hash"])
    )
    state = db.scalar(select(LoginAttempt).where(LoginAttempt.identity_hash == key).with_for_update())
    if state.locked_until and datetime.fromisoformat(state.locked_until) <= utcnow():
        state.failures, state.locked_until = 0, None
    ensure_not_locked(db, email)
    return state


def record_failure(db, state, user=None):
    state.failures += 1
    state.updated_at = stamp()
    if state.failures >= 5:
        state.locked_until = (utcnow() + timedelta(minutes=settings().account_lock_minutes)).isoformat()
    if user:
        user.failed_login_count, user.locked_until = state.failures, state.locked_until
    # Failed authentication must remain recorded even though the HTTP request is rejected.
    db.commit()
    raise DomainError(
        "Account temporarily locked. Try again after 15 minutes or contact your administrator."
        if state.failures >= 5
        else "Email or password is incorrect",
        423 if state.failures >= 5 else 401,
    )


def clear_failures(state, user):
    state.failures, state.locked_until, state.updated_at = 0, None, stamp()
    user.failed_login_count, user.locked_until = 0, None
