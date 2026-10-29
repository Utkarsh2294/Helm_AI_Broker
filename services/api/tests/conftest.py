import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def isolated_auth_limiter(monkeypatch):
    import fakeredis
    fake = fakeredis.FakeRedis()
    monkeypatch.setattr("app.auth.rate_limiter.redis_client", lambda: fake)
