import pytest
from sqlalchemy import select
from app import main, service
from app.config import settings
from app.core_client.client import CoreAPIClient
from app.db.models import Case, Job, utcnow
from app.db.store import save_snapshot, latest
from test_case_access import login
from test_core_lifecycle import send


@pytest.mark.parametrize("failed,complaint", [(False, False), (False, True), (True, False)])
def test_withdrawal_revocation_is_durable_bounded_and_runs_while_agents_paused(
    client, monkeypatch, failed, complaint
):
    headers = login(client)
    item = client.post(
        "/api/v1/demo/requests",
        headers=headers,
        json={"id": "withdraw-delivered", "name": "Fictional withdrawal"},
    ).json()
    with main.SessionLocal() as db:
        case = db.get(Case, item["id"])
        case.state = "COMPLAINT_FLAGGED" if complaint else "PUBLISHED"
        case.previous_state = "PUBLISHED" if complaint else None
        save_snapshot(db, case.id, "publication", {"recommendation_id": "fictional-recommendation"})
        db.commit()
    monkeypatch.setattr(settings(), "core_delivery_enabled", True)
    monkeypatch.setattr(settings(), "agents_paused", True)
    calls = []

    async def revoke(self, method, path, body, key):
        calls.append((method, path, key))
        if failed:
            raise ConnectionError("fictional unavailable Core")
        return {"status": "revoked"}

    monkeypatch.setattr(CoreAPIClient, "request", revoke)
    response = send(
        client,
        {"id": "withdraw-event", "type": "quote_request.withdrawn", "request_id": "withdraw-delivered"},
    )
    assert response.status_code == 200
    assert calls == []  # Signed webhook commits the outbox before delivery.
    with main.SessionLocal() as db:
        case = db.get(Case, item["id"])
        assert case.state == ("COMPLAINT_FLAGGED" if complaint else "CLOSED")
        if complaint:
            assert case.previous_state == "CLOSED"
        job = db.scalar(select(Job).where(Job.case_id == case.id, Job.kind == "revoke"))
        assert job.status == "pending"
        for _ in range(3 if failed else 1):
            job.due_at = utcnow().isoformat()
            db.flush()
            service.process_due_jobs(db, case.id)
            db.commit()
        assert job.status == ("needs_human" if failed else "completed")
        assert bool(latest(db, case.id, "revocation")) is not failed
        assert len(calls) == (3 if failed else 1) and len({call[2] for call in calls}) == 1
        service.process_due_jobs(db, case.id)
        assert len(calls) == (3 if failed else 1)
