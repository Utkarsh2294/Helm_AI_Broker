from app import main
from app.db.store import latest


def auth(client, email):
    result = client.post("/api/v1/auth/password", json={"email": email, "password": "HelmDemo!2026"})
    assert result.status_code == 200
    return {"X-CSRF-Token": result.json()["csrf"]}


def test_only_designated_compliance_owner_can_resolve_and_closure_is_immutable(client):
    headers = auth(client, "broker@helm.demo")
    item = client.get("/api/v1/cases").json()[0]
    url = "/api/v1/cases/" + item["id"]
    prior = client.get(url).json()["state"]
    response = client.post(
        url + "/complaint",
        headers=headers,
        json={"reason": "Fictional complaint details PRIVATE_COMPLAINT_CANARY"},
    )
    assert response.status_code == 200 and response.json()["complaint"]["owner_id"]
    assert response.json()["state"] == "COMPLAINT_FLAGGED"
    assert client.post(url + "/resume", headers=headers, json={}).status_code == 409
    resolution = {"resolution": "Fictional complaint investigated and resolved by the designated owner."}
    assert client.post(url + "/complaints/resolve", headers=headers, json=resolution).status_code == 403
    headers = auth(client, "compliance@helm.demo")
    result = client.post(url + "/complaints/resolve", headers=headers, json=resolution)
    assert result.status_code == 200 and result.json()["state"] == prior
    with main.SessionLocal() as db:
        record = latest(db, item["id"], "complaint_resolution")
        assert record.body["text"] == resolution["resolution"]
    assert "PRIVATE_COMPLAINT_CANARY" not in str(client.get(url + "/events").json())
