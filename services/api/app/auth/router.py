import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request, Response
from pydantic import Field
from sqlalchemy import select
from app.auth import authenticate, identity, public_user, verify_password
from app.auth import mfa, passkeys, sessions
from app.auth.rate_limiter import check_limit
from app.db.models import LoginSession, User, utcnow
from app.db.platform import SessionDevice, TOTPSecret, RefreshToken
from app.main import database
from app.schemas import Model, DomainError

router = APIRouter(prefix="/api/v1/auth")


class Login(Model):
    email: str = Field(default="broker@helm.demo", max_length=200)
    password: str = Field(min_length=1, max_length=256)


class OTP(Model):
    challenge_id: str = ""
    code: str = Field(min_length=6, max_length=16)


class Ceremony(Model):
    challenge_id: str
    credential: dict


class Options(Model):
    email: str = ""
    step_up: bool = False


class StepUp(Model):
    password: str = ""
    code: str = ""


def credential_access(db, request):
    user, current = identity(db, request)
    token = request.headers.get("X-Step-Up", "")
    if (
        not token
        or not current.step_up_at
        or utcnow() - datetime.fromisoformat(current.step_up_at) > timedelta(minutes=5)
    ):
        raise DomainError("Re-authenticate to change account security", 403, requires_step_up=True)
    try:
        proof = mfa.load_challenge(db, token, "step-up")
    except DomainError:
        raise DomainError("Re-authenticate to change account security", 403, requires_step_up=True)
    if proof.user_id != user.id or proof.body.get("session_id") != current.id:
        raise DomainError("Security verification belongs to a different session", 403, requires_step_up=True)
    return user, proof


@router.post("/identify")
def identify(body: Options):
    return {"methods": ["passkey", "password"]}


@router.post("/password")
@router.post("/login")
def login(body: Login, request: Request, response: Response, db=Depends(database, scope="function")):
    from app.auth.account_lock import ensure_not_locked

    ensure_not_locked(db, body.email)
    check_limit(request)
    user = authenticate(db, body.email, body.password)
    totp = db.get(TOTPSecret, user.id)
    if totp and totp.enabled:
        return {"requires_totp": True, "challenge_id": mfa.challenge(db, user.id, "totp-login")}
    return sessions.issue(db, user, request, response)


@router.post("/totp/verify")
def totp_login(body: OTP, request: Request, response: Response, db=Depends(database, scope="function")):
    check_limit(request, "totp")
    pending = mfa.load_challenge(db, body.challenge_id, "totp-login")
    mfa.verify_totp(db, pending.user_id, body.code)
    pending.consumed = True
    return sessions.issue(db, db.get(User, pending.user_id), request, response)


@router.post("/totp/setup")
def totp_setup(request: Request, db=Depends(database, scope="function")):
    user, _ = credential_access(db, request)
    return mfa.setup_totp(db, user)


@router.post("/totp/enable")
def totp_enable(body: OTP, request: Request, db=Depends(database, scope="function")):
    user, proof = credential_access(db, request)
    codes = mfa.enable_totp(db, user.id, body.code)
    proof.consumed = True
    return {"recovery_codes": codes}


@router.post("/recovery")
def recovery(body: OTP, request: Request, response: Response, db=Depends(database, scope="function")):
    check_limit(request, "recovery")
    pending = mfa.load_challenge(db, body.challenge_id, "totp-login")
    mfa.consume_recovery(db, pending.user_id, body.code)
    pending.consumed = True
    return sessions.issue(db, db.get(User, pending.user_id), request, response)


@router.post("/passkeys/register/options")
def register_options(request: Request, db=Depends(database, scope="function")):
    user, _ = credential_access(db, request)
    return passkeys.registration_options(db, user)


@router.post("/passkeys/register")
def register(body: Ceremony, request: Request, db=Depends(database, scope="function")):
    user, proof = credential_access(db, request)
    result = passkeys.register(db, user, body.challenge_id, body.credential)
    proof.consumed = True
    return result


@router.post("/passkey/options")
def auth_options(body: Options, request: Request, db=Depends(database, scope="function")):
    check_limit(request, "passkey-options", limit=20)
    if body.step_up:
        user, session = identity(db, request)
        return passkeys.authentication_options(db, user.id, session.id)
    return passkeys.authentication_options(db)


@router.post("/passkey/verify")
def verify(body: Ceremony, request: Request, response: Response, db=Depends(database, scope="function")):
    check_limit(request, "passkey-verify")
    user, step_session_id = passkeys.authenticate_passkey(db, body.challenge_id, body.credential)
    if step_session_id:
        current_user, current = identity(db, request)
        if current_user.id != user.id or current.id != step_session_id:
            raise DomainError("Step-up is bound to a different session", 403)
        current.step_up_at = utcnow().isoformat()
        return {
            "ok": True,
            "expires_in": 300,
            "step_up_token": mfa.challenge(db, user.id, "step-up", {"session_id": current.id}),
        }
    return sessions.issue(db, user, request, response)


@router.post("/step-up")
def step_up(body: StepUp, request: Request, db=Depends(database, scope="function")):
    user, session = identity(db, request)
    check_limit(request, "step-up")
    record = db.get(TOTPSecret, user.id)
    if record and record.enabled:
        mfa.verify_totp(db, user.id, body.code)
    elif not verify_password(body.password, user.password_hash):
        raise DomainError("Verify with your password or enrolled authenticator", 401)
    session.step_up_at = utcnow().isoformat()
    return {
        "ok": True,
        "expires_in": 300,
        "step_up_token": mfa.challenge(db, user.id, "step-up", {"session_id": session.id}),
    }


@router.get("/session")
def session(request: Request, db=Depends(database, scope="function")):
    user, row = identity(db, request)
    totp = db.get(TOTPSecret, user.id)
    return {
        "user": public_user(user),
        "csrf": row.csrf,
        "session_id": row.id,
        "totp_enabled": bool(totp and totp.enabled),
    }


@router.post("/refresh")
def refresh(request: Request, response: Response, db=Depends(database, scope="function")):
    cookie, header = request.cookies.get("helm_csrf", ""), request.headers.get("X-CSRF-Token", "")
    if not cookie or not secrets.compare_digest(cookie, header):
        raise DomainError("Invalid refresh CSRF token", 403)
    return sessions.rotate(db, request.cookies.get("helm_refresh", ""), request, response)


@router.post("/logout")
@router.post("/logout-all")
def logout(request: Request, response: Response, db=Depends(database, scope="function")):
    user, current = identity(db, request)
    if request.url.path.endswith("logout-all"):
        for token in db.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id)):
            token.revoked = True
        for session in db.scalars(select(LoginSession).where(LoginSession.user_id == user.id)):
            db.delete(session)
    else:
        for token in db.scalars(select(RefreshToken).where(RefreshToken.session_id == current.id)):
            token.revoked = True
        db.delete(current)
    for name in ("helm_session", "helm_refresh", "helm_csrf"):
        response.delete_cookie(name, path="/")
    return {"ok": True}


@router.get("/devices")
def devices(request: Request, db=Depends(database, scope="function")):
    user, current = identity(db, request)
    rows = db.execute(
        select(SessionDevice, LoginSession)
        .join(LoginSession, SessionDevice.session_id == LoginSession.id)
        .where(SessionDevice.user_id == user.id)
    ).all()
    return [
        {
            "id": device.session_id,
            "ip": device.ip,
            "user_agent": device.user_agent,
            "last_seen_at": device.last_seen_at,
            "current": device.session_id == current.id,
        }
        for device, _ in rows
    ]


@router.delete("/devices/{session_id}")
def revoke_device(session_id: str, request: Request, db=Depends(database, scope="function")):
    user, _ = identity(db, request)
    row = db.get(LoginSession, session_id)
    if not row or row.user_id != user.id:
        raise DomainError("Device not found", 404)
    db.delete(row)
    for token in db.scalars(select(RefreshToken).where(RefreshToken.session_id == row.id)):
        token.revoked = True
    return {"ok": True}
