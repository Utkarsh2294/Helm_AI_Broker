import base64
import json
from sqlalchemy import select
from webauthn import generate_registration_options, generate_authentication_options, options_to_json
from webauthn import verify_registration_response, verify_authentication_response
from webauthn.helpers.structs import AuthenticatorSelectionCriteria, ResidentKeyRequirement, UserVerificationRequirement
from app.auth.mfa import challenge, load_challenge
from app.config import settings
from app.db.models import User
from app.db.platform import Passkey
from app.schemas import DomainError


def encode(value):
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def decode(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def registration_options(db, user):
    options = generate_registration_options(rp_id=settings().rp_id, rp_name="Helm Broker", user_id=user.id.encode(),
        user_name=user.email, authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED, user_verification=UserVerificationRequirement.REQUIRED))
    data = json.loads(options_to_json(options))
    token = challenge(db, user.id, "register", {"challenge": data["challenge"]})
    return {"challenge_id": token, "options": data}


def register(db, user, token, credential):
    row = load_challenge(db, token, "register")
    if row.user_id != user.id:
        raise DomainError("Challenge belongs to another user", 403)
    try:
        verified = verify_registration_response(credential=credential, expected_challenge=decode(row.body["challenge"]),
            expected_rp_id=settings().rp_id, expected_origin=settings().allowed_origin, require_user_verification=True)
    except Exception:
        raise DomainError("Passkey registration could not be verified", 401)
    row.consumed = True
    db.add(Passkey(id=encode(verified.credential_id), user_id=user.id, public_key=encode(verified.credential_public_key),
                   sign_count=verified.sign_count))
    return {"ok": True}


def authentication_options(db, user_id=None, session_id=None):
    options = generate_authentication_options(rp_id=settings().rp_id, user_verification=UserVerificationRequirement.REQUIRED)
    data = json.loads(options_to_json(options))
    token = challenge(db, user_id, "passkey", {"challenge": data["challenge"], "session_id": session_id})
    return {"challenge_id": token, "options": data}


def authenticate_passkey(db, token, credential):
    row = load_challenge(db, token, "passkey")
    key = db.scalar(select(Passkey).where(Passkey.id == credential.get("id", "")).with_for_update())
    if not key or (row.user_id and row.user_id != key.user_id):
        raise DomainError("Passkey could not be verified", 401)
    try:
        verified = verify_authentication_response(credential=credential, expected_challenge=decode(row.body["challenge"]),
            expected_rp_id=settings().rp_id, expected_origin=settings().allowed_origin,
            credential_public_key=decode(key.public_key), credential_current_sign_count=key.sign_count,
            require_user_verification=True)
    except Exception:
        raise DomainError("Passkey could not be verified", 401)
    row.consumed = True
    key.sign_count = verified.new_sign_count
    return db.get(User, key.user_id), row.body.get("session_id")
