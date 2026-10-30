import json
from sqlalchemy.orm import Session
from app.db.models import Base, Case
from app.db.store import make_engine, audit


def test_only_committed_audit_metadata_is_published(tmp_path, monkeypatch):
    sent = []

    class Publisher:
        def publish(self, channel, body):
            sent.append((channel, json.loads(body)))

    monkeypatch.setattr("app.db.store.event_client", lambda: Publisher())
    engine = make_engine(f"sqlite:///{tmp_path / 'notifications.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        case = Case(core_request_id="notifications", profile={"name": "Fictional"})
        db.add(case)
        db.flush()
        audit(db, case.id, "committed_event", "system")
        assert not sent
        db.commit()
        assert len(sent) == 1 and sent[0][0] == f"case:{case.id}:events"
        assert sent[0][1]["seq"] == 1 and sent[0][1]["type"] == "committed_event"
        audit(db, case.id, "rolled_back_event", "system")
        db.rollback()
        assert len(sent) == 1
    engine.dispose()
