from fastapi.testclient import TestClient
from app.agents.quotation import PARTNERS
from app.config import settings
from tools.partner_sim import app, responses


def test_standalone_simulator_serves_all_five_fictional_partners():
    responses.clear()
    with TestClient(app) as client:
        assert client.get("/health").json()["partners"] == 5
        for partner in PARTNERS:
            reply = client.post("/rfq", json={"partner_id": partner["id"]})
            assert reply.status_code == 200
            assert len(reply.json()["quotes"]) == 6
            assert reply.json()["fictional"]
        assert client.post("/rfq", json={"partner_id": "unknown"}).status_code == 404


def test_controls_require_a_key_and_return_a_referral_without_quotes():
    responses.clear()
    try:
        with TestClient(app) as client:
            body = {"partner_id": PARTNERS[0]["id"], "type": "referral"}
            assert client.post("/rfq/set-response", json=body).status_code == 403
            assert (
                client.post(
                    "/rfq/set-response", json=body, headers={"X-Simulator-Key": settings().core_client_secret}
                ).status_code
                == 200
            )
            assert client.post("/rfq", json={"partner_id": body["partner_id"]}).json()["quotes"] == []
    finally:
        responses.clear()
