import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def isolated_auth_limiter(monkeypatch):
    import fakeredis

    fake = fakeredis.FakeRedis()
    monkeypatch.setattr("app.auth.rate_limiter.redis_client", lambda: fake)


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker
    from app import main
    from app.config import settings
    from app.db.models import Base
    from app.db.store import make_engine

    engine = make_engine(f"sqlite:///{tmp_path / 'api.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(engine, expire_on_commit=False))
    monkeypatch.setattr(settings(), "jwt_signing_key_file", str(tmp_path / "auth-signing.pem"))
    with TestClient(main.app) as instance:
        yield instance
    engine.dispose()
