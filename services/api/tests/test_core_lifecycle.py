from app.core_client.client import encode_event, sign
from app.config import settings
from app.db.models import utcnow
from test_governance_access import login


def send(client, event):
    raw = encode_event(event)
    timestamp = str(int(utcnow().timestamp()))
    return client.post(
        "/api/v1/webhooks/core",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Helm-Timestamp": timestamp,
            "X-Helm-Signature": sign(raw, timestamp, settings().core_webhook_secret),
        },
    )


def test_new_source_revision_invalidates_g0_and_withdrawal_cancels_work(client):
    headers = login(client, "broker@helm.demo")
    request = {
        "id": "revision-fixture",
        "name": "Fictional revisions",
        "needs": {"coverage": {"cancer": {"level": 3}}},
    }
    case = client.post("/api/v1/demo/requests", headers=headers, json=request).json()
    url = "/api/v1/cases/" + case["id"]
    assert client.post(url + "/sign-off", headers=headers, json={"dnr_acknowledged": True}).status_code == 200
    updated = {**request, "needs": {"budget_annual_pence": 160000, "coverage": {"cancer": {"level": 3}}}}
    event = {"id": "core-update-2", "type": "quote_request.updated", "revision": 2, "request": updated}
    assert send(client, event).status_code == 200
    current = client.get(url).json()
    assert current["state"] == "FACTFIND_REVIEW" and current["dnr"]["version"] == 2
    assert current["dnr"]["needs"]["budget_annual_pence"] == 160000
    assert client.post(url + "/release", headers=headers, json={}).status_code == 409
    assert send(client, {**event, "id": "same-revision-conflict", "request": request}).status_code == 409
    assert (
        send(
            client, {"id": "core-withdraw", "type": "quote_request.withdrawn", "request_id": request["id"]}
        ).status_code
        == 200
    )
    assert client.get(url).json()["state"] == "CLOSED"
    assert client.post(url + "/resume", headers=headers, json={}).status_code == 409
