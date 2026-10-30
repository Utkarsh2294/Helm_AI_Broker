from app.core_client.client import encode_event, sign
from app.db.models import utcnow
from app.config import settings
from test_governance_access import login


def test_signed_dissatisfaction_locks_agents_and_duplicate_is_idempotent(client):
    headers = login(client, "broker@helm.demo")
    case = client.get("/api/v1/cases").json()[0]
    raw = encode_event(
        {
            "id": "complaint-message-1",
            "type": "consumer.message_received",
            "case_id": case["id"],
            "text": "I am unhappy with how this was handled. PRIVATE_MESSAGE_CANARY",
        }
    )
    timestamp = str(int(utcnow().timestamp()))
    signed = {
        "Content-Type": "application/json",
        "X-Helm-Timestamp": timestamp,
        "X-Helm-Signature": sign(raw, timestamp, settings().core_webhook_secret),
    }
    response = client.post("/api/v1/webhooks/core", content=raw, headers=signed)
    assert response.status_code == 200, response.text
    assert client.post("/api/v1/webhooks/core", content=raw, headers=signed).json()["duplicate"]
    current = client.get("/api/v1/cases/" + case["id"]).json()
    assert current["state"] == "COMPLAINT_FLAGGED" and current["complaint"]["owner_id"]
    assert "PRIVATE_MESSAGE_CANARY" not in str(current["events"])
    assert client.post("/api/v1/cases/" + case["id"] + "/resume", headers=headers, json={}).status_code == 409
