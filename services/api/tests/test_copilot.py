from datetime import datetime, timezone
from sqlalchemy import select
from app import main
from app.db.copilot import Notification, CaseMetric
from app.db.store import audit
from app.copilot_projection import priority_score
from test_agentic_demo import ranked


def test_priority_deterministic():
    fixture = {
        "state": "PAUSED_NEEDS_HUMAN",
        "last_action_at": "2026-10-20T08:00:00+00:00",
        "coverage_type": "individual",
        "unrated_plan_fraction": 1,
    }
    now = datetime(2026, 10, 26, 8, tzinfo=timezone.utc)
    assert all(priority_score(fixture, now) == 360 for _ in range(50))
    assert priority_score({**fixture, "state": "BROKER_REVIEW", "unrated_plan_fraction": 0.5}, now) == 275


def test_transactional_case_notifications_and_non_medical_projection(client):
    headers, case = ranked(client)
    with main.SessionLocal() as db:
        metric = db.get(CaseMetric, case["id"])
        assert metric.state == "BROKER_REVIEW" and metric.body["plans"] == 5
        rows = db.scalars(select(Notification).where(Notification.case_id == case["id"])).all()
        assert {row.event_type for row in rows} >= {"case.created", "rating.unblocked"}
        assert all(row.broker_id == metric.broker_id for row in rows)
        before = len(rows)
        audit(db, case["id"], "fictional_rollback", "system", {"to": "PAUSED_NEEDS_HUMAN"})
        db.rollback()
        assert len(db.scalars(select(Notification).where(Notification.case_id == case["id"])).all()) == before
        assert "medical" not in str(metric.body).lower()
