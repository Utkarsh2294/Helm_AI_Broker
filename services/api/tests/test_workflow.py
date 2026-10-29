import pytest
from datetime import timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.auth import hasher
from app.db.models import Base, User, LoginSession, Approval, Activity, Job, utcnow
from app.db.store import latest, make_engine, verify_chain
from app.schemas import CoverageNeed, Needs, QuoteRequest, DomainError, State
from app import service


@pytest.fixture
def workspace(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'workflow.db'}")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        user = User(
            email="test@helm.demo",
            name="Broker",
            password_hash=hasher.hash("demo"),
            role="authorised_broker",
            can_approve=True,
            fca_irn="TEST-IRN",
        )
        db.add(user)
        db.add(User(email="owner@test.demo", name="Compliance", password_hash=user.password_hash, role="compliance_officer"))
        db.flush()
        session = LoginSession(
            id="s", user_id=user.id, csrf="c", expires_at=(utcnow() + timedelta(hours=1)).isoformat()
        )
        db.add(session)
        case = service.import_request(
            db,
            QuoteRequest(
                id="test",
                name="Demo",
                needs=Needs(coverage={"cancer": CoverageNeed(level=3, must_have=True)}),
            ),
        )
        db.commit()
        yield db, case, user, session


def ready_for_selection(db, case, user, session, scenario="happy"):
    service.act(db, case.id, "sign-off", user, session, {"dnr_acknowledged": True})
    service.act(db, case.id, "release", user, session, {"scenario": scenario})
    job = db.scalar(select(Job).where(Job.case_id == case.id))
    job.due_at = (utcnow() - timedelta(seconds=1)).isoformat()
    db.flush()
    service.process_due_jobs(db)
    return latest(db, case.id, "ranking")


def test_full_journey_binds_human_approval_to_latest_pack(workspace):
    db, case, user, session = workspace
    with pytest.raises(DomainError):
        service.act(db, case.id, "approve", user, session, {})
    ranking = ready_for_selection(db, case, user, session).body
    selected = [r["plan"]["id"] for r in ranking["top"][:3]]
    body = {
        "ranking_id": ranking["id"],
        "selected": selected,
        "survey": {"thumbs": dict.fromkeys(selected, "up")},
        "acknowledgements": selected,
    }
    service.act(db, case.id, "selection", user, session, body)
    pack = latest(db, case.id, "pack").body
    with pytest.raises(DomainError, match="Re-authenticate"):
        service.act(db, case.id, "approve", user, session, {"pack_hash": pack["pack_hash"]})
    session.step_up_at = utcnow().isoformat()
    from app.auth.mfa import challenge
    from app.agents.review import canonical_hash
    from app.db.store import save_snapshot
    pack = {**pack, "dnr_sections_confirmed": ["priorities", "coverage", "budget", "household", "medical_flag"],
            "unmet_needs_addressed": [f"{n['plan_id']}:{n['need']}" for n in pack["unmet_needs"]]}
    pack["pack_hash"] = canonical_hash({k: v for k, v in pack.items() if k != "pack_hash"})
    save_snapshot(db, case.id, "pack", pack)
    proof = challenge(db, user.id, "step-up", {"session_id": session.id})
    db.flush()
    with pytest.raises(DomainError, match="Pack changed"):
        service.act(db, case.id, "approve", user, session, {"pack_hash": "old", "step_up_token": proof})
    result = service.act(db, case.id, "approve", user, session, {"pack_hash": pack["pack_hash"], "step_up_token": proof})
    db.commit()
    assert result["state"] == State.PUBLISHED
    approval = db.scalar(select(Approval).where(Approval.gate == "G2"))
    assert approval.payload_hash == pack["pack_hash"] and approval.user_id == user.id
    events = db.scalars(select(Activity).where(Activity.case_id == case.id).order_by(Activity.seq)).all()
    assert verify_chain(events)


def test_complaint_locks_jobs_and_assistant_cannot_act(workspace):
    db, case, user, session = workspace
    user.role = "broker_assistant"
    with pytest.raises(DomainError):
        service.act(db, case.id, "sign-off", user, session, {})
    user.role = "authorised_broker"
    service.act(db, case.id, "sign-off", user, session, {"dnr_acknowledged": True})
    service.act(db, case.id, "release", user, session, {})
    service.act(db, case.id, "complaint", user, session, {})
    job = db.scalar(select(Job).where(Job.case_id == case.id))
    job.due_at = utcnow().isoformat()
    db.flush()
    service.process_due_jobs(db)
    assert case.state == State.COMPLAINT_FLAGGED and job.status == "pending"


def test_agent_cannot_cross_human_gate(workspace):
    db, case, user, session = workspace
    with pytest.raises(DomainError):
        service.transition(db, case, [case.state], State.AWAIT_BROKER_RELEASE, "fake", "agent:1")
    assert case.state == State.FACTFIND_REVIEW
