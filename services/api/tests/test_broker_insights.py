from datetime import timedelta
from sqlalchemy import select, text
from app import main
from app.db.models import User, Case, utcnow
from app.db.copilot import CaseMetric, CaseSatisfaction
from test_agentic_demo import ranked, login


def view():
    with main.SessionLocal() as db:
        db.execute(
            text(
                "CREATE VIEW IF NOT EXISTS mv_case_daily_stats AS SELECT substr(created_at,1,10) AS day,coverage_type,broker_id,insurer_id,count(*) AS new_cases,sum(CASE WHEN state IN ('PUBLISHED','CLOSED') THEN 1 ELSE 0 END) AS closed_cases,avg(close_days) AS avg_days_to_close FROM case_metrics GROUP BY 1,2,3,4"
            )
        )
        db.commit()


def test_scoped_dashboard_filters_exports_and_senior_productivity(client):
    headers, case = ranked(client)
    view()
    response = client.get("/api/v1/insights/dashboard")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["overview"]["cases"] >= 1 and data["productivity"] is None
    assert data["satisfaction"]["samples"] == 0 and data["cohorts"]["renewal_rate"] is None
    assert sum(row["new"] for row in data["volume"]["rows"]) == data["overview"]["cases"]
    assert "PRIVATE_MEDICAL" not in response.text and "medical_items" not in response.text
    assert client.get("/api/v1/insights/dashboard?coverage_type=invalid").status_code == 422
    assert client.get("/api/v1/insights/dashboard?from=2026-10-20&to=2026-01-01").status_code == 422
    assert client.get("/api/v1/insights/broker-productivity").status_code == 403
    with main.SessionLocal() as db:
        owner = db.get(Case, case["id"]).assigned_to
    pilot = login(client, "pilot@helm.demo")
    assert client.get("/api/v1/insights/dashboard?broker_id=" + owner).status_code == 403
    assert case["id"] not in str(client.get("/api/v1/insights/dashboard").json())
    with main.SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "pilot@helm.demo"))
        user.is_lead_broker = True
        db.commit()
    assert client.get("/api/v1/insights/dashboard?broker_id=" + owner).status_code == 200
    assert client.get("/api/v1/insights/broker-productivity?broker_id=all").status_code == 200
    for format, magic in [("pdf", b"%PDF"), ("csv", b"Metric,Value")]:
        exported = client.get("/api/v1/insights/scorecard?format=" + format)
        assert exported.status_code == 200 and exported.content.startswith(magic)
    summary = client.post("/api/v1/insights/summary", headers=pilot, json={})
    assert summary.status_code == 200 and summary.json()["actions_performed"] == []


def test_signed_consumer_satisfaction_is_real_scoped_and_idempotent(client):
    from test_consumer_events import published_fixture, send

    case_id, pack_hash = published_fixture()
    assert (
        send(
            client,
            case_id,
            pack_hash,
            "survey-1",
            "consumer.satisfaction",
            score=5,
            comment="PRIVATE_SURVEY_TEXT",
        ).status_code
        == 200
    )
    assert send(
        client,
        case_id,
        pack_hash,
        "survey-1",
        "consumer.satisfaction",
        score=5,
        comment="PRIVATE_SURVEY_TEXT",
    ).json()["duplicate"]
    assert send(client, case_id, pack_hash, "survey-1", "consumer.satisfaction", score=1).status_code == 409
    login(client)
    data = client.get("/api/v1/insights/satisfaction").json()
    assert data["samples"] == 1 and data["average"] == 5
    assert "PRIVATE_SURVEY_TEXT" not in str(data)
    with main.SessionLocal() as db:
        assert len(db.scalars(select(CaseSatisfaction)).all()) == 1
        assert db.get(CaseMetric, case_id).csat == 5


def test_priority_queue_cursor_and_aging_match_task_formula(client):
    from app.copilot_projection import priority_score

    headers, case = ranked(client)
    with main.SessionLocal() as db:
        metric = db.get(CaseMetric, case["id"])
        metric.last_action_at = (utcnow() - timedelta(days=7)).isoformat()
        # A projection fixture represents an old intake without changing immutable evidence.
        old = db.get(Case, case["id"])
        old.created_at = (utcnow() - timedelta(days=11)).isoformat()
        metric.created_at = old.created_at
        db.commit()
        expected = priority_score(
            {
                "state": metric.state,
                "coverage_type": metric.coverage_type,
                "last_action_at": metric.last_action_at,
                "unrated_plan_fraction": 1,
            },
            utcnow(),
        )
    response = client.get("/api/v1/cases?sort=priority&age_range=10%2B&limit=1")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["items"][0]["id"] == case["id"]
    assert abs(data["items"][0]["priority_score"] - expected) < 0.00001
    assert not client.get("/api/v1/cases?age_range=0-2").json() or all(
        row["id"] != case["id"] for row in client.get("/api/v1/cases?age_range=0-2").json()
    )
    assert client.get("/api/v1/cases?age_range=bogus").status_code == 422
