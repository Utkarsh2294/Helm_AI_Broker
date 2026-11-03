"""The saved feed is authoritative; notification delivery is added to this writer."""

from sqlalchemy import select, func
from app.db.policy_buying import BuyingRead, BuyingUpdate
from app.db.store import audit, next_case_time


def record_update(db, buying, kind, message, actor="demo-agent", **metadata):
    seq = (db.scalar(select(func.max(BuyingUpdate.seq)).where(BuyingUpdate.pb_case_id == buying.id)) or 0) + 1
    row = BuyingUpdate(
        pb_case_id=buying.id,
        seq=seq,
        update_type=kind,
        body={"message": message, "actor": actor, **metadata},
        created_at=next_case_time(db, buying.case_id),
    )
    db.add(row)
    db.flush()
    buying.updated_at = row.created_at
    audit(db, buying.case_id, f"pb.{kind}", actor, {"pb_case_id": buying.id, "update_seq": seq})
    return row


def mark_read(db, buying_id, user_id, seq):
    latest = db.scalar(select(func.max(BuyingUpdate.seq)).where(BuyingUpdate.pb_case_id == buying_id)) or 0
    row = db.get(BuyingRead, (buying_id, user_id))
    if row is None:
        row = BuyingRead(pb_case_id=buying_id, user_id=user_id, seq=0)
        db.add(row)
    row.seq = max(row.seq, min(seq, latest))
    return row.seq
