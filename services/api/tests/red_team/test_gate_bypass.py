from copy import deepcopy
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from sqlalchemy.orm import sessionmaker
from app import main, service
from app.auth import digest
from app.auth.mfa import challenge
from app.db.models import Base, Case, LoginSession, Publication, Activity, utcnow
from app.db.store import make_engine, save_snapshot
from app.schemas import DomainError
from app.agents.review import canonical_hash


@pytest.fixture(scope="module")
def factory(tmp_path_factory):
    engine = make_engine(f"sqlite:///{tmp_path_factory.mktemp('redteam') / 'api.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(main, "SessionLocal", factory)
        yield factory
    engine.dispose()


@pytest.mark.parametrize("number", range(50))
def test_fifty_gate_bypasses_never_publish(factory, number):
    group = (
        "agent"
        if number < 10
        else "assistant"
        if number < 20
        else "missing"
        if number < 30
        else "expired"
        if number < 40
        else "cross_case"
        if number < 45
        else "wrong_hash"
    )
    with TestClient(main.app) as client:
        email = "assistant@helm.demo" if group == "assistant" else "broker@helm.demo"
        login = client.post("/api/v1/auth/password", json={"email": email, "password": "HelmDemo!2026"})
        assert login.status_code == 200
        headers = {"X-CSRF-Token": login.json()["csrf"]}
        with factory() as db:
            case = Case(
                core_request_id=f"attack-{number}",
                profile={"name": "Test", "cover_type": "individual"},
                state="AWAIT_APPROVAL",
            )
            db.add(case)
            db.flush()
            body = {"ranking_id": f"ranking-{number}", "test": "server-held pack"}
            body["pack_hash"] = canonical_hash(body)
            save_snapshot(db, case.id, "pack", body)
            session = db.get(LoginSession, digest(client.cookies.get("helm_session")))
            proof = ""
            if group in ("expired", "cross_case", "wrong_hash"):
                session.step_up_at = (
                    utcnow() - timedelta(minutes=6) if group == "expired" else utcnow()
                ).isoformat()
                proof = challenge(db, session.user_id, "step-up", {"session_id": session.id})
            db.commit()
            case_id = case.id
            if group == "agent":
                with pytest.raises(DomainError) as error:
                    service.transition(db, case, [case.state], "PUBLISHED", "forged", f"agent:{number}")
                assert error.value.status == 403
            else:
                submitted = body["pack_hash"]
                if group == "cross_case":
                    other = Case(core_request_id=f"other-{number}", profile={"name": "Other"})
                    db.add(other)
                    db.flush()
                    other_body = {**deepcopy(body), "ranking_id": f"other-ranking-{number}"}
                    other_body["pack_hash"] = canonical_hash(
                        {k: v for k, v in other_body.items() if k != "pack_hash"}
                    )
                    save_snapshot(db, other.id, "pack", other_body)
                    db.commit()
                    submitted = other_body["pack_hash"]
                elif group == "wrong_hash":
                    submitted = "0" * 64
                response = client.post(
                    f"/api/v1/cases/{case_id}/approve",
                    json={"pack_hash": submitted, "step_up_token": proof},
                    headers=headers,
                )
                assert response.status_code in (401, 403, 409), response.text
            db.expire_all()
            assert db.get(Case, case_id).state != "PUBLISHED"
            assert not db.scalar(
                select(func.count()).select_from(Publication).where(Publication.case_id == case_id)
            )
            assert db.scalar(
                select(Activity).where(Activity.case_id == case_id, Activity.type == "GATE_VIOLATION")
            )
