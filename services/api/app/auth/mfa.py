import json
import secrets
import string
from datetime import datetime, timedelta
import pyotp
from sqlalchemy import select
from app.auth import digest, hasher, verify_password
from app.db.models import utcnow
from app.db.platform import AuthChallenge, TOTPSecret
from app.schemas import DomainError


def challenge(db, user_id, purpose, body=None):
    raw = secrets.token_urlsafe(32)
    db.add(
        AuthChallenge(
            id=digest(raw),
            user_id=user_id,
            purpose=purpose,
            body=body or {},
            expires_at=(utcnow() + timedelta(minutes=5)).isoformat(),
        )
    )
    return raw


def load_challenge(db, raw, purpose):
    row = db.scalar(select(AuthChallenge).where(AuthChallenge.id == digest(raw)).with_for_update())
    if (
        not row
        or row.consumed
        or row.purpose != purpose
        or datetime.fromisoformat(row.expires_at) <= utcnow()
    ):
        raise DomainError("Expired or used authentication challenge", 401)
    return row


def verify_totp(db, user_id, code):
    record = db.scalar(select(TOTPSecret).where(TOTPSecret.user_id == user_id).with_for_update())
    if not record:
        raise DomainError("Enroll an authenticator first", 409)
    totp = pyotp.TOTP(record.body["secret"])
    counter = int(utcnow().timestamp() // 30)
    for offset in (-1, 0, 1):
        tick = counter + offset
        if tick > record.last_counter and secrets.compare_digest(totp.generate_otp(tick), str(code)):
            record.last_counter = tick
            return record
    raise DomainError("Invalid or already-used authenticator code", 401)


def setup_totp(db, user):
    previous = db.get(TOTPSecret, user.id)
    if previous and previous.enabled:
        raise DomainError("Authenticator already enrolled; verify before replacing it")
    secret = pyotp.random_base32()
    if previous:
        previous.body = {"secret": secret}
    else:
        db.add(TOTPSecret(user_id=user.id, body={"secret": secret}))
    return {
        "secret": secret,
        "uri": pyotp.TOTP(secret).provisioning_uri(user.email, issuer_name="Helm Broker"),
    }


def enable_totp(db, user_id, code):
    record = verify_totp(db, user_id, code)
    codes = [
        "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8)) for _ in range(10)
    ]
    record.enabled = True
    record.body = {**record.body, "recovery": [{"hash": hasher.hash(c), "used": False} for c in codes]}
    return codes


def consume_recovery(db, user_id, code):
    record = db.scalar(select(TOTPSecret).where(TOTPSecret.user_id == user_id).with_for_update())
    if not record or not record.enabled:
        raise DomainError("Invalid recovery code", 401)
    data = json.loads(json.dumps(record.body))
    for entry in data.get("recovery", []):
        if not entry["used"] and verify_password(code.upper(), entry["hash"]):
            entry["used"] = True
            record.body = data
            return
    raise DomainError("Invalid or used recovery code", 401)
