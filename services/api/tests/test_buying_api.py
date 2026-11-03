import pytest
from sqlalchemy import select, text
from app import main
from app.agents.review import canonical_hash
from app.db.models import Approval, Case, Publication, User
from app.db.store import save_snapshot
from test_agentic_demo import login


def buying_fixture(client, basis="moratorium", suffix="", quote_basis=None):
    headers = login(client)
    with main.SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "broker@helm.demo"))
        case = Case(
            core_request_id="buying-" + basis + suffix,
            state="PUBLISHED",
            assigned_to=user.id,
            profile={
                "name": "Fictional Buying Client",
                "postcode": "M20",
                "coverage_type": "individual",
                "consumer_reference": "buying-person-" + basis,
            },
        )
        db.add(case)
        db.flush()
        save_snapshot(
            db, case.id, "dnr", {"consent_to_share": True, "needs": {"preferred_underwriting": basis}}
        )
        plan = {
            "id": "fixture-plan",
            "name": "Demo Health",
            "insurerId": "northgate",
            "annualPremiumPence": 86200,
            "excessPence": 10000,
            "coverage": {"cancer": 3, "outpatient": 2},
            "hospitalListLevel": 3,
            "underwritingType": quote_basis or basis,
            "status": "quoted",
        }
        body = {"selected": [plan["id"]], "plans": [{"plan": plan}]}
        body["pack_hash"] = canonical_hash(body)
        save_snapshot(db, case.id, "pack", body)
        approval = Approval(case_id=case.id, gate="G2", user_id=user.id, payload_hash=body["pack_hash"])
        db.add(approval)
        db.flush()
        db.add(Publication(case_id=case.id, approval_id=approval.id, pack_hash=body["pack_hash"]))
        db.commit()
        return (
            headers,
            case.id,
            {"selected_plan_id": plan["id"], "pack_hash": body["pack_hash"], "confirm_selection": True},
        )


def test_demo_selection_is_scoped_explicit_and_idempotent(client):
    headers, case_id, choice = buying_fixture(client)
    url = f"/api/v1/consumer/cases/{case_id}/select-quote"
    assert client.post(url, headers=headers, json={**choice, "confirm_selection": False}).status_code == 422
    assert (
        client.post(url, headers=headers, json={**choice, "selected_plan_id": "unknown"}).status_code == 422
    )
    assert client.post(url, headers=headers, json={**choice, "pack_hash": "a" * 64}).status_code == 409
    response = client.post(url, headers=headers, json=choice)
    assert response.status_code == 200, response.text
    assert client.post(url, headers=headers, json=choice).json()["id"] == response.json()["id"]
    login(client, "pilot@helm.demo")
    assert client.get(f"/api/v1/policy-buying/choices/{case_id}").status_code == 404


def current(client, case_id):
    response = client.get(f"/api/v1/policy-buying/cases/{case_id}")
    assert response.status_code == 200, response.text
    return response.json()


def act(client, headers, case_id, path, kind=None, **extra):
    item = current(client, case_id)
    body = {"expected_version": item["version"], **extra}
    if kind:
        body["document_id"] = next(row["id"] for row in item["documents"] if row["doc_type"] == kind)
    response = client.post(f"/api/v1/policy-buying/cases/{case_id}/{path}", headers=headers, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def step_up(client, headers):
    result = client.post("/api/v1/auth/step-up", headers=headers, json={"password": "HelmDemo!2026"})
    assert result.status_code == 200, result.text
    return result.json()["step_up_token"]


@pytest.mark.parametrize("basis", ["moratorium", "fmu"])
def test_both_buying_branches_issue_once_without_sensitive_data_leaks(client, monkeypatch, basis):
    headers, case_id, choice = buying_fixture(client, basis)
    monkeypatch.setattr(
        "app.service.invoke", lambda *a, **k: pytest.fail("Buying must not send completed answers to agents")
    )
    assert (
        client.post(
            f"/api/v1/consumer/cases/{case_id}/select-quote", headers=headers, json=choice
        ).status_code
        == 200
    )
    before = current(client, case_id)
    assert before["stage"] == "IPID_DRAFTING"
    assert {row["doc_type"] for row in before["documents"]} == {
        "ipid",
        "toba",
        "moratorium_declaration" if basis == "moratorium" else "fmu_questionnaire",
    }
    act(client, headers, case_id, "baseline")
    act(client, headers, case_id, "documents/ipid/send", "ipid")
    act(client, headers, case_id, "documents/ipid/respond", "ipid", decision="confirm")
    act(client, headers, case_id, "documents/toba/send", "toba")
    act(client, headers, case_id, "documents/toba/respond", "toba", decision="confirm")
    kind = "moratorium_declaration" if basis == "moratorium" else "fmu_questionnaire"
    act(client, headers, case_id, f"documents/{kind}/send", kind)
    act(client, headers, case_id, "declaration/complete", kind, confirm_signature=True)
    if basis == "fmu":
        assert client.get(f"/api/v1/policy-buying/cases/{case_id}/medical-response").status_code == 403
        item = current(client, case_id)
        doc_id = next(row["id"] for row in item["documents"] if row["doc_type"] == kind)
        denied = client.post(
            f"/api/v1/policy-buying/cases/{case_id}/declaration/approve",
            headers=headers,
            json={"expected_version": item["version"], "document_id": doc_id},
        )
        assert denied.status_code == 403
        proof = step_up(client, headers)
        assert (
            client.post(
                f"/api/v1/cases/{case_id}/medical-access", headers={**headers, "X-Step-Up": proof}
            ).status_code
            == 200
        )
        response = client.get(f"/api/v1/policy-buying/cases/{case_id}/medical-response")
        assert response.status_code == 200 and "no-store" in response.headers["cache-control"]
        assert "Seeded fictional entry" in response.text
        assert "Seeded fictional entry" not in str(current(client, case_id))
    act(client, headers, case_id, "declaration/approve", kind)
    act(client, headers, case_id, "banking/complete", "banking_request", confirm_signature=True)
    assert "00001234" not in str(current(client, case_id))
    proof = step_up(client, headers)
    reveal_headers = {**headers, "X-Step-Up": proof}
    raw = act(client, reveal_headers, case_id, "banking/reveal")
    assert raw["account_number"] == "00001234"
    proof = step_up(client, headers)
    item = current(client, case_id)
    repeated = client.post(
        f"/api/v1/policy-buying/cases/{case_id}/banking/reveal",
        headers={**headers, "X-Step-Up": proof},
        json={"expected_version": item["version"]},
    )
    assert repeated.status_code == 409
    act(client, headers, case_id, "banking/verify")
    assert current(client, case_id)["stage"] == "SUBMISSION_PACKAGE_READY"
    act(client, headers, case_id, "submission/review", "submission_package")
    item = current(client, case_id)
    package_id = next(row["id"] for row in item["documents"] if row["doc_type"] == "submission_package")
    payload = {
        "expected_version": item["version"],
        "document_id": package_id,
        "package_hash": item["package_hash"],
        "confirm_send": True,
    }
    url = f"/api/v1/policy-buying/cases/{case_id}/submission/send"
    import time

    start = time.perf_counter()
    result = client.post(url, headers=headers, json=payload)
    assert result.status_code == 200, result.text
    assert time.perf_counter() - start < 5
    assert result.json()["policy_number"].startswith("DEMO-NORTHGATE-")
    assert (
        client.post(url, headers=headers, json=payload).json()["policy_number"]
        == result.json()["policy_number"]
    )
    completed = current(client, case_id)
    assert completed["closed_at"] and completed["stage"] == "POLICY_ISSUED"
    assert completed["confirmation_message"]["delivery"] == "local_demo_outbox_only"
    order = [row["type"] for row in reversed(completed["feed"])]
    assert order.index("declaration_approved") < order.index("banking_requested")
    assert order.index("banking_verified") < order.index("submission_ready")
    assert order.index("sent_to_insurer") < order.index("policy_issued")
    assert case_id not in {row["case_id"] for row in client.get("/api/v1/policy-buying").json()["items"]}
    assert case_id in {
        row["case_id"] for row in client.get("/api/v1/policy-buying?closed=true").json()["items"]
    }
    assert "00001234" not in str(completed) and "Seeded fictional entry" not in str(completed)
    with main.SessionLocal() as db:
        assert db.get(Case, case_id).state == "CLOSED"
        assert "00001234" not in str(db.execute(text("SELECT body FROM pb_banking_details")).all())


def test_ipid_change_invalidates_confirmation_and_stale_versions(client):
    headers, case_id, choice = buying_fixture(client)
    client.post(f"/api/v1/consumer/cases/{case_id}/select-quote", headers=headers, json=choice)
    old = current(client, case_id)
    doc = next(row for row in old["documents"] if row["doc_type"] == "ipid")
    denied = client.post(
        f"/api/v1/policy-buying/cases/{case_id}/documents/ipid/send",
        headers=headers,
        json={"expected_version": old["version"], "document_id": doc["id"]},
    )
    assert denied.status_code == 409
    act(client, headers, case_id, "baseline")
    stale = client.post(
        f"/api/v1/policy-buying/cases/{case_id}/baseline",
        headers=headers,
        json={"expected_version": old["version"]},
    )
    assert stale.status_code == 409
    act(client, headers, case_id, "documents/ipid/send", "ipid")
    act(
        client,
        headers,
        case_id,
        "documents/ipid/respond",
        "ipid",
        decision="change",
        note="Please clarify the hospital list",
    )
    assert current(client, case_id)["pending_response"]
    assert case_id in {
        row["id"] for row in client.get("/api/v1/cases?sort=priority&limit=50").json()["items"]
    }
    assert any(row["case_id"] == case_id for row in client.get("/api/v1/tasks/rail").json()["items"])
    act(
        client,
        headers,
        case_id,
        "documents/ipid/edit",
        "ipid",
        instruction="Section Where am I covered?: UK-only fictional treatment; consult the insurer terms.",
    )
    item = current(client, case_id)
    changed = next(row for row in item["documents"] if row["doc_type"] == "ipid")
    assert changed["version"] == 2 and changed["status"] == "draft"
    assert len([row for row in item["history"] if row["doc_type"] == "ipid"]) == 2
    result = client.post(
        f"/api/v1/policy-buying/cases/{case_id}/documents/ipid/respond",
        headers=headers,
        json={"expected_version": item["version"], "document_id": doc["id"], "decision": "confirm"},
    )
    assert result.status_code == 409


def test_quote_cannot_silently_change_fact_find_underwriting(client):
    headers, case_id, choice = buying_fixture(client, quote_basis="FMU")
    response = client.post(f"/api/v1/consumer/cases/{case_id}/select-quote", headers=headers, json=choice)
    assert response.status_code == 409 and "differs" in response.text
    assert client.get(f"/api/v1/policy-buying/cases/{case_id}").status_code == 404


def test_unchanged_toba_is_reused_only_for_the_same_stable_consumer(client):
    headers, first, choice = buying_fixture(client)
    client.post(f"/api/v1/consumer/cases/{first}/select-quote", headers=headers, json=choice)
    act(client, headers, first, "baseline")
    act(client, headers, first, "documents/ipid/send", "ipid")
    act(client, headers, first, "documents/ipid/respond", "ipid", decision="confirm")
    act(client, headers, first, "documents/toba/send", "toba")
    act(client, headers, first, "documents/toba/respond", "toba", decision="confirm")
    headers, second, choice = buying_fixture(client, suffix="-repeat")
    client.post(f"/api/v1/consumer/cases/{second}/select-quote", headers=headers, json=choice)
    act(client, headers, second, "baseline")
    act(client, headers, second, "documents/ipid/send", "ipid")
    act(client, headers, second, "documents/ipid/respond", "ipid", decision="confirm")
    item = current(client, second)
    assert next(row for row in item["documents"] if row["doc_type"] == "toba")["status"] == "confirmed"
    assert any(row["type"] == "standing_toba_reused" for row in item["feed"])
    headers, other, choice = buying_fixture(client, basis="fmu")
    client.post(f"/api/v1/consumer/cases/{other}/select-quote", headers=headers, json=choice)
    act(client, headers, other, "baseline")
    act(client, headers, other, "documents/ipid/send", "ipid")
    act(client, headers, other, "documents/ipid/respond", "ipid", decision="confirm")
    assert (
        next(row for row in current(client, other)["documents"] if row["doc_type"] == "toba")["status"]
        == "draft"
    )


def test_other_brokers_cannot_read_buying_documents_or_mutate_the_case(client):
    headers, case_id, choice = buying_fixture(client)
    client.post(f"/api/v1/consumer/cases/{case_id}/select-quote", headers=headers, json=choice)
    item = current(client, case_id)
    doc = next(row for row in item["documents"] if row["doc_type"] == "ipid")
    other = login(client, "pilot@helm.demo")
    assert client.get(f"/api/v1/policy-buying/cases/{case_id}").status_code == 404
    assert client.get(f"/api/v1/policy-buying/cases/{case_id}/documents/{doc['id']}.pdf").status_code == 404
    assert (
        client.post(
            f"/api/v1/policy-buying/cases/{case_id}/baseline",
            headers=other,
            json={"expected_version": item["version"]},
        ).status_code
        == 404
    )
    assert case_id not in str(client.get("/api/v1/policy-buying").json())
