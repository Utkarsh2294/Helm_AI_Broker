import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db.models import Base, Case
from app.db.store import audit, make_engine, save_snapshot, verify_chain


def test_encryption_append_only_and_audit(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        case = Case(core_request_id="test", profile={"name": "Private Demo"})
        db.add(case)
        db.flush()
        snapshot = save_snapshot(db, case.id, "dnr", {"medical_items": ["PRIVATE MEDICAL TEXT"]})
        first = audit(db, case.id, "received", "system")
        second = audit(db, case.id, "intake", "agent:1")
        db.commit()
        raw = db.execute(text("SELECT body FROM snapshots")).scalar()
        assert "PRIVATE MEDICAL TEXT" not in raw
        assert snapshot.body["medical_items"] == ["PRIVATE MEDICAL TEXT"]
        assert verify_chain([first, second])
        second.payload = {"tampered": True}
        assert not verify_chain([first, second])
        with pytest.raises(ValueError, match="append-only"):
            db.flush()
