import json
from app import main
from app.schemas import State


def login(client):
    response = client.post(
        "/api/v1/auth/password", json={"email": "broker@helm.demo", "password": "HelmDemo!2026"}
    )
    return {"X-CSRF-Token": response.json()["csrf"]}


def test_ambiguous_wording_halts_before_any_crew_and_requires_a_recorded_review(client, monkeypatch):
    from app import service
    from app.db.store import latest

    calls = []
    monkeypatch.setattr(service, "invoke", lambda *args: calls.append(args))
    headers = login(client)
    response = client.post(
        "/api/v1/demo/requests",
        headers=headers,
        json={
            "id": "medical-halt-e2e",
            "name": "Fictional review subject",
            "medical_items": ["Maybe asthma."],
            "needs": {"coverage": {"outpatient": {"level": 2}}},
        },
    )
    assert response.status_code == 200
    case = response.json()
    url = "/api/v1/cases/" + case["id"]
    assert not calls
    assert case["state"] == State.PAUSED_NEEDS_HUMAN
    assert case["medical_triage"]["code"] == "H5"
    assert "Maybe asthma." not in json.dumps(case)
    assert client.post(url + "/resume", headers=headers, json={}).status_code == 409
    body = {
        "decision": "record_declared",
        "reason": "Reviewed the verbatim source with the consumer; no clinical conclusion inferred.",
    }
    assert client.post(url + "/medical-review", headers=headers, json=body).status_code == 403
    proof = client.post("/api/v1/auth/step-up", headers=headers, json={"password": "HelmDemo!2026"}).json()[
        "step_up_token"
    ]
    assert client.post(url + "/medical-access", headers={**headers, "X-Step-Up": proof}).status_code == 200
    assert (
        client.post(url + "/medical-review", headers=headers, json={**body, "reason": " " * 40}).status_code
        == 422
    )
    reviewed = client.post(url + "/medical-review", headers=headers, json=body)
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["state"] == State.FACTFIND_REVIEW
    assert reviewed.json()["medical_review"]["reason"] == "[REDACTED]"
    assert client.post(url + "/sign-off", headers=headers, json={"dnr_acknowledged": True}).status_code == 200
    with main.SessionLocal() as db:
        dnr = latest(db, case["id"], "dnr").body
        assert dnr["record"]["broker_ref"]
        assert dnr["record"]["budget_confirmed"]
        assert latest(db, case["id"], "medical_review").body["reason"] == body["reason"]


def test_fact_find_changes_have_server_authored_provenance_and_reset_confirmation(client):
    headers = login(client)
    cases = client.get("/api/v1/cases").json()
    case = next(
        client.get("/api/v1/cases/" + row["id"]).json()
        for row in cases
        if row["state"] == State.FACTFIND_REVIEW
    )
    dnr = case["dnr"]
    dnr["needs"]["hospital_level"] = 3
    dnr["facts"]["budget_annual_pence"]["source"] = "forged-client-source"
    dnr["record"]["broker_ref"] = "forged-broker"
    result = client.patch(
        "/api/v1/cases/" + case["id"] + "/dnr",
        headers=headers,
        json={"dnr": dnr, "reason": "Consumer confirmed the hospital network preference."},
    )
    assert result.status_code == 200, result.text
    saved = result.json()["dnr"]
    assert saved["facts"]["hospital_level"]["source"].startswith("broker_edit:")
    assert saved["facts"]["budget_annual_pence"]["source"] != "forged-client-source"
    assert saved["record"]["broker_ref"] is None
    assert saved["record"]["budget_confirmed"] is False
