from datetime import timedelta
from types import SimpleNamespace
import fitz
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.models import Base, Case, Activity, User, utcnow
from app.db.store import make_engine, audit, save_snapshot, verify_chain
from app.evidence import generate, pdf_bytes, replay


def test_hundred_chains_and_twenty_historical_cases(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'evidence.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        auditor = User(email="audit@test.demo", name="Audit", password_hash="not-used", role="auditor")
        db.add(auditor)
        for i in range(100):
            case = Case(core_request_id=f"case-{i}", profile={"name": "Fictional", "cover_type": "individual"})
            db.add(case)
            db.flush()
            audit(db, case.id, "received", "system", {"to": "RECEIVED"})
            marker = audit(db, case.id, "intake_started", "system", {"from": "RECEIVED", "to": "INTAKE_RUNNING"})
            save_snapshot(db, case.id, "dnr", {"medical_items": ["HEALTH_CANARY"], "version": 1})
            audit(db, case.id, "intake_completed", "agent:1", {"from": "INTAKE_RUNNING", "to": "FACTFIND_REVIEW"})
            rows = db.scalars(select(Activity).where(Activity.case_id == case.id).order_by(Activity.seq)).all()
            assert verify_chain(rows)
            corrupted = [SimpleNamespace(**{k: getattr(r, k) for k in ("case_id", "seq", "actor", "type", "payload", "created_at", "prev_hash", "hash")}) for r in rows]
            corrupted[-1].hash = "bad"
            assert not verify_chain(corrupted)
            if i < 20:
                from datetime import datetime
                old = replay(db, case, datetime.fromisoformat(marker.created_at), auditor)
                assert old["historical"] and old["state"] == "INTAKE_RUNNING" and old["dnr"] is None
        data = generate(db, case, auditor, include_medical=True)
        assert "HEALTH_CANARY" not in str(data)
        assert len(data["compliance_checklist"]) == 18
        path = tmp_path / "evidence.pdf"
        path.write_bytes(pdf_bytes(data))
        doc = fitz.open(path)
        text = "\n".join(page.get_text() for page in doc)
        assert len(doc) >= 15
        for i in range(1, 15):
            assert f"{i:02d} /" in text
        assert "HEALTH_CANARY" not in text
        doc.close()
    engine.dispose()
