from sqlalchemy import select
from app import main
from app.agents.review import canonical_hash
from app.db.models import Approval, Case, Publication, User
from app.db.store import save_snapshot
from test_agentic_demo import login


def buying_fixture(client, basis="moratorium"):
    headers = login(client)
    with main.SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "broker@helm.demo"))
        case = Case(
            core_request_id="buying-" + basis,
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
            "underwritingType": basis,
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
