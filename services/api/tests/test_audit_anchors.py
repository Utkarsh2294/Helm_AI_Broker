from sqlalchemy.orm import sessionmaker
from app import audit_jobs
from app.config import settings
from app.db.models import Base, Case
from app.db.store import make_engine, audit


def test_independent_anchor_copy_is_not_overwritten_and_tampering_creates_p1_alert(tmp_path, monkeypatch):
    engine = make_engine(f"sqlite:///{tmp_path / 'anchors.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(audit_jobs, "SessionLocal", factory)
    directory = tmp_path / "write-once"
    monkeypatch.setattr(settings(), "audit_anchor_directory", str(directory))
    with factory() as db:
        case = Case(core_request_id="anchor-fixture", profile={"name": "Fictional"})
        db.add(case)
        db.flush()
        audit(db, case.id, "received", "system")
        db.commit()
        case_id = case.id
    first = audit_jobs.verify_all()
    anchor = next(directory.glob("????-??-??.json"))
    original = anchor.read_bytes()
    with factory() as db:
        audit(db, case_id, "later_event", "system")
        db.commit()
    second = audit_jobs.verify_all()
    assert not second["alert_raised"] and anchor.read_bytes() == original
    assert first["anchored_root_hash"] == second["anchored_root_hash"]
    anchor.write_bytes(b"altered independent copy")
    detected = audit_jobs.verify_all()
    assert detected["alert_raised"] and detected["anchor_failures"][0]["code"] == "anchor_copy_mismatch"
    assert list(directory.glob("alert-*.json"))
    assert anchor.read_bytes() == b"altered independent copy"
    engine.dispose()
