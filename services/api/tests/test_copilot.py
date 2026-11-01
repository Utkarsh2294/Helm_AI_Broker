from datetime import datetime, timezone
from sqlalchemy import select
from app import main
from app.db.models import utcnow
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


def test_task_notification_endpoints_are_scoped_and_snoozes_expire(client):
    from test_agentic_demo import login
    from app.db.copilot import TaskSnooze
    from datetime import timedelta

    headers, case = ranked(client)
    task = next(t for t in client.get("/api/v1/tasks/rail").json()["items"] if t["case_id"] == case["id"])
    assert task["task_key"] == "select_policies" and task["total"] == 5
    assert client.get("/api/v1/dashboard/priority-summary").json()["action_needed"] > 0
    explained = client.post(
        "/api/v1/assistant/explain-task",
        headers=headers,
        json={"case_id": case["id"], "task_key": task["task_key"]},
    )
    assert explained.status_code == 200 and explained.json()["actions_performed"] == []
    assert (
        client.post(
            f"/api/v1/tasks/{case['id']}/{task['task_key']}/snooze",
            headers=headers,
            json={"reason": "waiting_on_insurer_docs"},
        ).status_code
        == 200
    )
    assert not any(t["case_id"] == case["id"] for t in client.get("/api/v1/tasks/rail").json()["items"])
    with main.SessionLocal() as db:
        snooze = db.scalar(select(TaskSnooze).where(TaskSnooze.case_id == case["id"]))
        snooze.snoozed_until = (utcnow() - timedelta(seconds=1)).isoformat()
        db.commit()
    assert any(t["case_id"] == case["id"] for t in client.get("/api/v1/tasks/rail").json()["items"])
    inbox = client.get("/api/v1/notifications").json()
    own = next(n for n in inbox["items"] if n["case_id"] == case["id"])
    assert client.post(f"/api/v1/notifications/{own['id']}/read", headers=headers).status_code == 200
    pilot = login(client, "pilot@helm.demo")
    assert case["id"] not in str(client.get("/api/v1/tasks/rail").json())
    assert case["id"] not in str(client.get("/api/v1/notifications").json())
    assert client.post(f"/api/v1/notifications/{own['id']}/read", headers=pilot).status_code == 404
    assert client.get("/api/v1/tasks/rail?broker_id=" + own.get("broker_id", "other")).status_code == 403


def test_one_stream_lease_and_broker_rate_limit(client):
    from app.copilot_api import claim_stream
    from app.db.models import User
    from app.schemas import DomainError
    from app.assistant_security import rate_limit
    import pytest

    with main.SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "broker@helm.demo"))
        claim_stream(db, user)
        db.commit()
        with pytest.raises(DomainError, match="already open"):
            claim_stream(db, user)
        for _ in range(30):
            rate_limit(user.id)
        with pytest.raises(DomainError) as error:
            rate_limit(user.id)
        assert error.value.status == 429 and error.value.flags["retry_after"] == 60


def test_preview_operational_jobs_match_worker_and_are_idempotent(client):
    from app.copilot_jobs import preview_operational
    from app.db.copilot import SatisfactionDrivers
    from app.db.models import User

    preview_operational(main.SessionLocal, refresh=True, drivers=True)
    with main.SessionLocal() as db:
        before = {row.id for row in db.scalars(select(Notification))}
        user = db.scalar(select(User).where(User.email == "broker@helm.demo"))
        assert db.get(SatisfactionDrivers, user.id).body["status"] == "not_enough_observations"
    preview_operational(main.SessionLocal, refresh=True, drivers=True)
    with main.SessionLocal() as db:
        assert {row.id for row in db.scalars(select(Notification))} == before
