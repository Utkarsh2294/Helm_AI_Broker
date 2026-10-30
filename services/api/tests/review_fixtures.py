"""Explicit fictional human assessments for service-level workflow fixtures."""

from sqlalchemy import select
from app.db.platform import BrokerRating, CasePlan
from app.db.store import latest
from app.plan_ratings import draft_text
from app.agents.review import canonical_hash


def record_reviews(db, case_id, user, ranking):
    snapshot = latest(db, case_id, "ranking")
    for row in ranking["top"]:
        plan_id = row["plan"]["id"]
        plan = db.scalar(select(CasePlan).where(CasePlan.case_id == case_id, CasePlan.plan_id == plan_id))
        body = {
            "reason_text": "Fictional broker reviewed this plan against the recorded needs and trade-offs.",
            "ai_draft_text": draft_text(row),
        }
        db.add(
            BrokerRating(
                case_id=case_id,
                ranking_id=ranking["id"],
                ranking_snapshot_id=snapshot.id,
                plan_record_id=plan.id,
                plan_id=plan_id,
                broker_id=user.id,
                stars=4,
                decision="YES",
                body=body,
                is_edited=True,
                chars_changed=80,
                version=1,
                body_hash=canonical_hash(body),
            )
        )
    db.flush()
