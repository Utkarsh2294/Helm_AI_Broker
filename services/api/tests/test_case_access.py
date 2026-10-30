from datetime import timedelta
from sqlalchemy import select
from app import main
from app.auth import hasher
from app.db.models import Case, User, utcnow


def login(client, email="broker@helm.demo"):
    response = client.post("/api/v1/auth/password", json={"email": email, "password": "HelmDemo!2026"})
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf"]}


def test_assigned_case_is_private_in_detail_list_events_audit_and_insights(client):
    login(client)
    case_id = client.get("/api/v1/cases").json()[0]["id"]
    with main.SessionLocal() as db:
        other = User(
            email="other@helm.demo",
            name="Fictional colleague",
            password_hash=hasher.hash("HelmDemo!2026"),
            role="authorised_broker",
        )
        db.add(other)
        db.flush()
        db.get(Case, case_id).assigned_to = other.id
        db.commit()
    assert case_id not in [c["id"] for c in client.get("/api/v1/cases").json()]
    assert client.get(f"/api/v1/cases/{case_id}").status_code == 404
    assert client.get(f"/api/v1/cases/{case_id}/events").status_code == 404
    assert client.get(f"/api/v1/cases/{case_id}/evidence").status_code == 404
    assert client.get(f"/api/v1/audit/search?case_id={case_id}").json()["items"] == []
    assert client.get("/api/v1/insights").json()["cases"] == 2
    login(client, "compliance@helm.demo")
    assert client.get(f"/api/v1/cases/{case_id}").status_code == 200


def test_cursor_does_not_repeat_a_case_when_new_rows_arrive_and_rejects_tampering(client):
    headers = login(client)
    first = client.get("/api/v1/cases?limit=1").json()
    assert first["next_cursor"]
    created = client.post(
        "/api/v1/demo/requests",
        headers=headers,
        json={"id": "cursor-new", "name": "Fictional new arrival", "needs": {"coverage": {}}},
    )
    assert created.status_code == 200
    next_page = client.get("/api/v1/cases", params={"limit": 1, "cursor": first["next_cursor"]}).json()
    assert next_page["items"][0]["id"] != first["items"][0]["id"]
    assert (
        client.get("/api/v1/cases", params={"limit": 1, "cursor": first["next_cursor"] + "x"}).status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/cases", params={"limit": 1, "cursor": first["next_cursor"], "q": "different"}
        ).status_code
        == 422
    )
    login(client, "assistant@helm.demo")
    assert client.get("/api/v1/cases", params={"limit": 1, "cursor": first["next_cursor"]}).status_code == 422


def test_medical_access_requires_consent_role_fresh_step_up_and_the_same_session(client):
    headers = login(client)
    case = client.post(
        "/api/v1/demo/requests",
        headers=headers,
        json={
            "id": "medical-grant",
            "name": "Fictional medical applicant",
            "medical_items": ["PHI_CANARY_GRANT_6301"],
            "needs": {"coverage": {}},
        },
    ).json()
    url = f"/api/v1/cases/{case['id']}"
    assert client.get(url).json()["dnr"]["medical_items"] == ["[REDACTED]"]
    assert client.get(url + "?include_medical=true").status_code == 403
    proof = client.post("/api/v1/auth/step-up", headers=headers, json={"password": "HelmDemo!2026"}).json()[
        "step_up_token"
    ]
    granted = client.post(url + "/medical-access", headers={**headers, "X-Step-Up": proof})
    assert granted.status_code == 200
    assert client.get(url + "?include_medical=true").json()["dnr"]["medical_items"] == [
        "PHI_CANARY_GRANT_6301"
    ]
    assert client.post(url + "/medical-access", headers={**headers, "X-Step-Up": proof}).status_code == 403
    with main.SessionLocal() as db:
        from app.db.platform import MedicalAccess

        grant = db.scalar(select(MedicalAccess))
        grant.expires_at = (utcnow() - timedelta(seconds=1)).isoformat()
        db.commit()
    assert client.get(url + "?include_medical=true").status_code == 403
    login(client)
    assert client.get(url + "?include_medical=true").status_code == 403
    login(client, "assistant@helm.demo")
    assert client.get(url + "?include_medical=true").status_code == 403


def test_copied_medical_text_is_redacted_from_other_free_text_fields():
    from types import SimpleNamespace
    from app.compliance.medical_firewall import safe_case

    source = {
        "dnr": {"medical_items": ["Fictional medical canary"]},
        "pack": {"note": "Review FICTIONAL MEDICAL CANARY before deciding"},
    }
    assert (
        "FICTIONAL MEDICAL CANARY"
        not in safe_case(source, SimpleNamespace(role="authorised_broker"))["pack"]["note"]
    )
    assert source["pack"]["note"].endswith("before deciding")


def test_invalid_signed_core_submission_is_a_validation_error_not_a_server_error(client):
    from app.core_client.client import encode_event, sign
    from app.config import settings

    body = encode_event({"id": "invalid-core-structure", "type": "quote_request.submitted"})
    timestamp = str(int(utcnow().timestamp()))
    response = client.post(
        "/api/v1/webhooks/core",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Helm-Timestamp": timestamp,
            "X-Helm-Signature": sign(body, timestamp, settings().core_webhook_secret),
        },
    )
    assert response.status_code == 422
