from sqlalchemy import select
from app import main
from app.db.models import ModelProposal, User
from review_governance_fixtures import eligible_proposal
from test_governance_access import login


def test_proposer_cannot_self_approve_and_ordinary_brokers_cannot_propose(client):
    headers = login(client, "broker@helm.demo")
    assert client.post("/api/v1/models/evaluate", headers=headers).status_code == 403
    headers = login(client, "compliance@helm.demo")
    result = client.post("/api/v1/models/evaluate", headers=headers)
    assert result.status_code == 200 and result.json()["proposed_by"]
    with main.SessionLocal() as db:
        reviewer = db.scalar(select(User).where(User.email == "compliance@helm.demo"))
        row = ModelProposal(status="proposed", body={**eligible_proposal(), "proposed_by": reviewer.id})
        db.add(row)
        db.commit()
        url = f"/api/v1/mcr/{row.id}/approve"
    proof = client.post("/api/v1/auth/step-up", headers=headers, json={"password": "HelmDemo!2026"}).json()[
        "step_up_token"
    ]
    blocked = client.post(url, headers={**headers, "X-Step-Up": proof})
    assert blocked.status_code == 403 and "proposer" in blocked.json()["detail"]
