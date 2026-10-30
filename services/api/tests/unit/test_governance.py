import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.auth import hasher
from app.db.models import Base, User, Case, ModelProposal
from app.db.platform import EngineModel, ShadowEvaluation, ModelApproval
from app.db.store import make_engine, save_snapshot
from app.engine.ranking import user_weights
from app.schemas import DomainError
from app import governance


def test_independent_g5_shadow_metrics_promotion_and_rollback(tmp_path, monkeypatch):
    engine = make_engine(f"sqlite:///{tmp_path / 'governance.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        compliance = User(
            email="c@test.demo",
            name="Compliance",
            role="compliance_officer",
            password_hash=hasher.hash("test"),
        )
        lead = User(
            email="l@test.demo",
            name="Lead",
            role="authorised_broker",
            is_lead_broker=True,
            password_hash=hasher.hash("test"),
        )
        db.add_all([compliance, lead])
        proposal = ModelProposal(
            status="proposed", body={"eligible_for_shadow": True, "weights": user_weights([])}
        )
        db.add(proposal)
        db.flush()
        with pytest.raises(DomainError, match="Compliance must"):
            governance.approve_shadow(db, proposal.id, lead)
        governance.approve_shadow(db, proposal.id, compliance)
        db.flush()
        with pytest.raises(DomainError, match="independent"):
            governance.approve_shadow(db, proposal.id, compliance)
        governance.approve_shadow(db, proposal.id, lead)
        db.flush()
        model = db.scalar(select(EngineModel).where(EngineModel.status == "challenger"))
        assert governance.champion(db).version == "user-v1"
        with pytest.raises(DomainError, match="30 new"):
            governance.promote(db, proposal.id, compliance)
        for i in range(30):
            case = Case(core_request_id=f"shadow-{i}", profile={"name": "Test"})
            db.add(case)
            db.flush()
            save_snapshot(db, case.id, "selection", {"ranking_id": f"rank-{i}", "selected": ["a", "b", "c"]})
            db.add(
                ShadowEvaluation(
                    model_id=model.id,
                    case_id=case.id,
                    body={
                        "ranking_id": f"rank-{i}",
                        "champion": ["c", "b", "a"],
                        "challenger": ["a", "b", "c"],
                    },
                )
            )
        db.flush()
        with monkeypatch.context() as patch:
            patch.setattr(
                governance,
                "shadow_metrics",
                lambda *args: {"labelled_cases": 30, "champion_ndcg3": 0.8, "challenger_ndcg3": 0.81},
            )
            with pytest.raises(DomainError, match="0.02"):
                governance.promote(db, proposal.id, compliance)
        governance.promote(db, proposal.id, compliance)
        db.flush()
        assert governance.champion(db).version == "user-v1"
        governance.promote(db, proposal.id, lead)
        db.flush()
        assert governance.champion(db).id == model.id
        assert len(db.scalars(select(ModelApproval)).all()) == 4
        governance.rollback(db, model.id, compliance)
        db.flush()
        assert governance.champion(db).version == "user-v1"
    engine.dispose()
