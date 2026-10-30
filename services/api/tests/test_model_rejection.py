from sqlalchemy import select
from app import main
from app.db.models import ModelProposal
from app.db.platform import GovernanceEvent
from review_governance_fixtures import eligible_proposal
from test_governance_access import login


def test_rejection_is_verified_reasoned_and_cannot_later_be_approved(client):
    headers = login(client, "compliance@helm.demo")
    with main.SessionLocal() as db:
        row = ModelProposal(status="proposed", body=eligible_proposal())
        db.add(row)
        db.commit()
        pid = row.id
    url = "/api/v1/mcr/" + pid
    proof = client.post("/api/v1/auth/step-up", headers=headers, json={"password": "HelmDemo!2026"}).json()[
        "step_up_token"
    ]
    signed = {**headers, "X-Step-Up": proof}
    assert client.post(url + "/reject", headers=signed, json={"reason": "too short"}).status_code == 422
    reason = "The evidence is not representative enough for this fictional trial."
    assert (
        client.post(url + "/reject", headers=signed, json={"reason": reason}).json()["status"] == "rejected"
    )
    fresh = client.post("/api/v1/auth/step-up", headers=headers, json={"password": "HelmDemo!2026"}).json()[
        "step_up_token"
    ]
    assert client.post(url + "/approve", headers={**headers, "X-Step-Up": fresh}).status_code == 409
    with main.SessionLocal() as db:
        assert db.get(ModelProposal, pid).body["rejection"]["reason"] == reason
        assert reason not in str([r.body for r in db.scalars(select(GovernanceEvent))])
