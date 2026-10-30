from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
from app import main
from app.db.models import Base, LoginSession
from app.db.store import make_engine


def test_login_is_committed_before_success_reaches_the_client(tmp_path, monkeypatch):
    engine = make_engine(f"sqlite:///{tmp_path / 'response-commit.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", factory)
    observed = []

    async def observe_response(scope, receive, send):
        async def observe(message):
            if (
                scope.get("path") == "/api/v1/auth/password"
                and message["type"] == "http.response.start"
                and message["status"] == 200
            ):
                # A separate connection must already see the session when the cookie is sent.
                with factory() as reader:
                    observed.append(reader.scalar(select(func.count()).select_from(LoginSession)))
            await send(message)

        await main.app(scope, receive, observe)

    try:
        with TestClient(observe_response) as client:
            response = client.post(
                "/api/v1/auth/password",
                json={"email": "broker@helm.demo", "password": "HelmDemo!2026"},
            )
            assert response.status_code == 200
        assert observed == [1]
    finally:
        engine.dispose()
