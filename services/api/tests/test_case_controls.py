from app import main
from app.db.models import User
from test_case_access import login


def test_case_controls_are_versioned_role_scoped_and_preserve_human_gates(client):
    headers = login(client)
    case = client.get("/api/v1/cases").json()[0]
    url = f"/api/v1/cases/{case['id']}"
    original = client.get(url).json()
    body = {
        "operation": "priority",
        "expected_version": original["version"],
        "reason": "Client requested an earlier review of these fictional details.",
        "priority": "urgent",
    }
    changed = client.post(url + "/controls", headers=headers, json=body)
    assert changed.status_code == 200 and changed.json()["priority"] == "urgent"
    assert changed.json()["state"] == original["state"]
    assert client.post(url + "/controls", headers=headers, json=body).status_code == 409
    with main.SessionLocal() as db:
        other = db.query(User).filter_by(email="pilot@helm.demo").one()
        other_id = other.id
    current = client.get(url).json()
    body.update(operation="assign", expected_version=current["version"], assignee_id=other_id)
    assert client.post(url + "/controls", headers=headers, json=body).status_code == 403
    headers = login(client, "lead@helm.demo")
    assert client.post(url + "/controls", headers=headers, json=body).status_code == 200
    assert client.get(url).json()["state"] == original["state"]
    headers = login(client)
    assert client.get(url).status_code == 404
    headers = login(client, "pilot@helm.demo")
    current = client.get(url).json()
    body.update(operation="takeover", expected_version=current["version"])
    assert client.post(url + "/controls", headers=headers, json=body).status_code == 409
    assert body["reason"] not in str(current["events"])
    headers = login(client, "assistant@helm.demo")
    assert client.post(url + "/controls", headers=headers, json=body).status_code == 403
