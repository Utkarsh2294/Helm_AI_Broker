import pytest
import pyotp
import fakeredis
from fastapi import Request, Response
from sqlalchemy.orm import Session
from app.auth import hasher
from app.auth.mfa import setup_totp, enable_totp, verify_totp, consume_recovery
from app.auth.sessions import issue, rotate
from app.auth.rate_limiter import check_limit
from app.db.models import Base, User
from app.db.store import make_engine
from app.schemas import DomainError


def request():
    return Request(
        {"type": "http", "method": "POST", "path": "/", "headers": [], "client": ("127.0.0.50", 1)}
    )


def test_totp_recovery_and_replay(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'mfa.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(email="mfa@test.demo", name="Test", password_hash=hasher.hash("Password"))
        db.add(user)
        db.flush()
        data = setup_totp(db, user)
        codes = enable_totp(db, user.id, pyotp.TOTP(data["secret"]).now())
        assert len(codes) == 10
        with pytest.raises(DomainError):
            verify_totp(db, user.id, pyotp.TOTP(data["secret"]).now())
        consume_recovery(db, user.id, codes[0])
        with pytest.raises(DomainError):
            consume_recovery(db, user.id, codes[0])


def test_refresh_reuse_revokes_family(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'sessions.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(email="sessions@test.demo", name="Test", password_hash=hasher.hash("Password"))
        db.add(user)
        db.flush()
        response = Response()
        issue(db, user, request(), response)
        cookies = response.headers.getlist("set-cookie")
        raw = next(c for c in cookies if c.startswith("helm_refresh=")).split(";")[0].split("=", 1)[1]
        db.commit()
        rotate(db, raw, request(), Response())
        db.commit()
        with pytest.raises(DomainError, match="reuse"):
            rotate(db, raw, request(), Response())


def test_shared_limiter_after_five_attempts(monkeypatch):
    fake = fakeredis.FakeRedis()
    monkeypatch.setattr("app.auth.rate_limiter.redis_client", lambda: fake)
    for _ in range(5):
        check_limit(request())
    with pytest.raises(DomainError) as error:
        check_limit(request())
    assert error.value.status == 429
