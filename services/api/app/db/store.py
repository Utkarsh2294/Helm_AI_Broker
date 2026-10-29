from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker, Session
from redis import Redis
import json
import logging
from app.agents.review import canonical_hash
from app.config import settings
from app.db.models import Activity, Base, Snapshot, stamp


def make_engine(url=None):
    url = url or settings().database_url
    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def pragmas(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=10000")
    return engine


engine = make_engine()
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def create_tables():
    Base.metadata.create_all(engine)


def latest(db, case_id, kind):
    return db.scalar(select(Snapshot).where(Snapshot.case_id == case_id, Snapshot.kind == kind)
                     .order_by(Snapshot.version.desc()).limit(1))


def save_snapshot(db, case_id, kind, body):
    previous = latest(db, case_id, kind)
    snapshot = Snapshot(case_id=case_id, kind=kind, version=previous.version + 1 if previous else 1,
                        body=body, body_hash=canonical_hash(body))
    db.add(snapshot)
    db.flush()
    return snapshot


def audit(db, case_id, event_type, actor, payload=None):
    previous = db.scalar(select(Activity).where(Activity.case_id == case_id).order_by(Activity.seq.desc()).limit(1))
    body = {"case_id": case_id, "seq": previous.seq + 1 if previous else 1,
            "actor": actor, "type": event_type, "payload": payload or {}, "created_at": stamp()}
    prev_hash = previous.hash if previous else "0" * 64
    row = Activity(**body, prev_hash=prev_hash, hash=canonical_hash({"prev_hash": prev_hash, **body}))
    db.add(row)
    db.flush()
    db.info.setdefault("events_to_publish", []).append({**body, "hash": row.hash})
    return row


@event.listens_for(Session, "after_commit")
def publish_committed_events(db):
    events = db.info.pop("events_to_publish", [])
    if events:
        try:
            with Redis.from_url(settings().redis_url, socket_connect_timeout=0.2, socket_timeout=0.2) as redis:
                for item in events:
                    redis.publish(f"case:{item['case_id']}:events", json.dumps(item))
        except Exception:
            logging.getLogger("helm.audit").warning("event_publication_deferred", extra={"count": len(events)})


@event.listens_for(Session, "after_rollback")
def discard_rolled_back_events(db):
    db.info.pop("events_to_publish", None)


def verify_chain(events):
    previous = "0" * 64
    for i, row in enumerate(events, 1):
        body = {k: getattr(row, k) for k in ("case_id", "seq", "actor", "type", "payload", "created_at")}
        if row.seq != i or row.prev_hash != previous or row.hash != canonical_hash({"prev_hash": previous, **body}):
            return False
        previous = row.hash
    return True
