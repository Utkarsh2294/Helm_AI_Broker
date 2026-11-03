import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.db.models import Base, Case
from app.db.policy_buying import BuyingCase


def test_buying_storage_encrypts_selection_and_rejects_invalid_basis():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        case = Case(core_request_id="buying-storage", profile={"name": "Fictional"})
        db.add(case)
        db.flush()
        buying = BuyingCase(
            case_id=case.id,
            selected_plan_id="demo",
            underwriting_basis="moratorium",
            body={"name": "Private fixture"},
        )
        db.add(buying)
        db.commit()
        stored = db.scalar(text("SELECT body FROM policy_buying_cases"))
        assert "Private fixture" not in stored
        assert db.get(BuyingCase, buying.id).body["name"] == "Private fixture"
        buying.underwriting_basis = "unknown"
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
    engine.dispose()
