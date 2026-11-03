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
    notify_update(db, buying, row)
    return row


def notify_update(db, buying, row):
    import json
    from sqlalchemy import text
    from app.db.models import Case, User
    from app.db.copilot import Notification

    case = db.get(Case, buying.case_id)
    recipients = db.scalars(
        select(User).where(
            User.is_active.is_(True),
            User.id == case.assigned_to if case.assigned_to else User.role == "authorised_broker",
        )
    )
    kinds = {
        "ipid_generated": "pb.ipid_ready",
        "consumer_responded": "pb.consumer_responded",
        "declaration_completed": "pb.declaration_completed",
        "banking_received": "pb.banking_received",
        "submission_ready": "pb.submission_ready",
        "policy_issued": "pb.policy_issued",
    }
    if row.update_type not in kinds:
        return
    for user in recipients:
        notification = Notification(
            broker_id=user.id,
            case_id=case.id,
            event_key=f"pb:{row.id}",
            event_type=kinds[row.update_type],
            body={
                "title": "Policy Buying update",
                "message": row.body["message"],
                "href": f"/policy-buying/cases/{case.id}",
            },
        )
        db.add(notification)
        db.flush()
        if db.bind.dialect.name == "postgresql":
            db.execute(
                text("SELECT pg_notify('broker_events', :payload)"),
                {
                    "payload": json.dumps(
                        {"broker_id": user.id, "notification_id": notification.id, "case_id": case.id}
                    )
                },
            )


def mark_read(db, buying_id, user_id, seq):
    latest = db.scalar(select(func.max(BuyingUpdate.seq)).where(BuyingUpdate.pb_case_id == buying_id)) or 0
    row = db.get(BuyingRead, (buying_id, user_id))
    if row is None:
        row = BuyingRead(pb_case_id=buying_id, user_id=user_id, seq=0)
        db.add(row)
    row.seq = max(row.seq, min(seq, latest))
    return row.seq
