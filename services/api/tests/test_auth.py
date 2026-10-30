from datetime import timedelta
import jwt
import pytest
from freezegun import freeze_time
from sqlalchemy import select
from app import main
from app.auth import digest
from app.auth.tokens import verify_token
from app.db.models import LoginSession, User, utcnow
from app.schemas import DomainError


def sign_in(client, password="HelmDemo!2026", email="broker@helm.demo"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def test_access_cookie_is_rs256_and_has_a_fifteen_minute_lifetime(client):
    response = sign_in(client)
    assert response.status_code == 200
    raw = client.cookies.get("helm_session")
    assert jwt.get_unverified_header(raw)["alg"] == "RS256"
    claims = verify_token(raw)
    assert claims["exp"] - claims["iat"] == 900
    assert "httponly" in response.headers.get_list("set-cookie")[0].lower()
    assert "access_token" not in response.json()
    assert client.get("/api/v1/auth/session").status_code == 200


@pytest.mark.parametrize("email", ["broker@helm.demo", "unknown@fictional.invalid"])
def test_five_failures_lock_the_identity_without_account_enumeration(client, email):
    assert [sign_in(client, "incorrect", email).status_code for _ in range(5)] == [401, 401, 401, 401, 423]
    assert sign_in(client, email=email).status_code == 423
    with freeze_time(utcnow() + timedelta(minutes=16)):
        response = sign_in(client, email=email)
        assert response.status_code == (401 if email.startswith("unknown") else 200)


def test_failed_attempts_survive_the_rejected_http_transaction(client):
    assert sign_in(client, "incorrect").status_code == 401
    with main.SessionLocal() as db:
        assert db.scalar(select(User).where(User.email == "broker@helm.demo")).failed_login_count == 1
    assert sign_in(client).status_code == 200
    with main.SessionLocal() as db:
        assert db.scalar(select(User).where(User.email == "broker@helm.demo")).failed_login_count == 0


def test_expired_jwt_is_rejected_and_refresh_rotates_the_session(client):
    login = sign_in(client).json()
    previous = client.cookies.get("helm_session")
    with freeze_time(utcnow() + timedelta(minutes=16)):
        assert client.get("/api/v1/auth/session").status_code == 401
        refreshed = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": login["csrf"]})
        assert refreshed.status_code == 200
        assert client.cookies.get("helm_session") != previous
        assert client.get("/api/v1/auth/session").status_code == 200


def test_step_up_jwt_is_separate_and_expires_in_five_minutes(client):
    login = sign_in(client).json()
    response = client.post(
        "/api/v1/auth/step-up", json={"password": "HelmDemo!2026"}, headers={"X-CSRF-Token": login["csrf"]}
    )
    assert response.status_code == 200
    raw = response.json()["step_up_token"]
    claims = verify_token(raw, "step-up")
    assert claims["su"] and claims["exp"] - claims["iat"] == 300
    with pytest.raises(DomainError):
        verify_token(raw)
    with freeze_time(utcnow() + timedelta(minutes=6)), pytest.raises(DomainError) as error:
        verify_token(raw, "step-up")
    assert error.value.status == 403


def test_disabled_staff_cannot_start_or_continue_sessions(client):
    assert sign_in(client).status_code == 200
    with main.SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "broker@helm.demo"))
        user.is_active = False
        db.commit()
    assert client.get("/api/v1/auth/session").status_code == 401
    assert sign_in(client).status_code == 403


def test_legacy_opaque_session_survives_until_its_record_expires(client):
    with main.SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "broker@helm.demo"))
        db.add(
            LoginSession(
                id=digest("legacy-opaque-fixture"),
                user_id=user.id,
                csrf="legacy",
                expires_at=(utcnow() + timedelta(minutes=10)).isoformat(),
            )
        )
        db.commit()
    client.cookies.set("helm_session", "legacy-opaque-fixture")
    assert client.get("/api/v1/auth/session").status_code == 200


def test_hmac_forgery_cannot_replace_an_rsa_access_token(client):
    sign_in(client)
    raw = client.cookies.get("helm_session")
    claims = jwt.decode(raw, options={"verify_signature": False})
    forged = jwt.encode(
        claims, "F" * 64, algorithm="HS256", headers={"kid": jwt.get_unverified_header(raw)["kid"]}
    )
    with pytest.raises(DomainError) as error:
        verify_token(forged)
    assert error.value.status == 401


def test_credential_enrollment_requires_fresh_session_bound_step_up(client):
    login = sign_in(client).json()
    headers = {"X-CSRF-Token": login["csrf"]}
    assert client.post("/api/v1/auth/totp/setup", headers=headers).status_code == 403
    proof = client.post("/api/v1/auth/step-up", json={"password": "HelmDemo!2026"}, headers=headers).json()[
        "step_up_token"
    ]
    assert client.post("/api/v1/auth/totp/setup", headers={**headers, "X-Step-Up": proof}).status_code == 200
    with freeze_time(utcnow() + timedelta(minutes=6)):
        assert (
            client.post(
                "/api/v1/auth/passkeys/register/options", headers={**headers, "X-Step-Up": proof}
            ).status_code
            == 403
        )
