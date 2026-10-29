import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from app import main
from app.db.models import Base
from app.db.store import make_engine


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = make_engine(f"sqlite:///{tmp_path / 'api.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(engine, expire_on_commit=False))
    main.attempts.clear()
    with TestClient(main.app) as client:
        yield client
    engine.dispose()


def login(client, email="broker@helm.demo"):
    response = client.post("/api/v1/auth/password", json={"email": email, "password": "HelmDemo!2026"})
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf"]}


def test_auth_csrf_origin_and_logout(client):
    assert client.get("/api/v1/cases").status_code == 401
    assert client.post("/api/v1/auth/password", json={"password": "wrong"}).status_code == 401
    headers = login(client)
    cases = client.get("/api/v1/cases").json()
    case_id = cases[0]["id"]
    endpoint = f"/api/v1/cases/{case_id}/sign-off"
    assert client.post(endpoint, json={}).status_code == 403
    assert client.post(endpoint, json={}, headers={**headers, "Origin": "https://attacker.example"}).status_code == 403
    assert client.post(endpoint, json={"actor": "broker:pretend"}, headers=headers).status_code == 422
    assert client.post(endpoint, json={"dnr_acknowledged": True}, headers=headers).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/v1/cases").status_code == 401


def test_assistant_cannot_cross_gate_and_import_is_idempotent(client):
    headers = login(client, "auditor@helm.demo")
    case_id = client.get("/api/v1/cases").json()[0]["id"]
    assert client.post(f"/api/v1/cases/{case_id}/sign-off", json={}, headers=headers).status_code == 403
    client.post("/api/v1/auth/logout", headers=headers)
    headers = login(client)
    request = {"id": "duplicate", "name": "Fictional Import", "needs": {"coverage": {"cancer": {"level": 3}}}}
    first = client.post("/api/v1/demo/requests", json=request, headers=headers)
    second = client.post("/api/v1/demo/requests", json=request, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert len(first.json()["events"]) == len(second.json()["events"])
