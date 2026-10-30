from sqlalchemy import select
from app import main
from app.db.models import ModelProposal
from app.db.platform import ModelApproval
from app.engine.ranking import user_weights


def login(client, email):
    result = client.post("/api/v1/auth/password", json={"email": email, "password": "HelmDemo!2026"})
    assert result.status_code == 200
    return {"X-CSRF-Token": result.json()["csrf"]}


def test_g5_requires_single_use_session_bound_verification(client):
    headers = login(client, "compliance@helm.demo")
    with main.SessionLocal() as db:
        proposal = ModelProposal(
            status="proposed", body={"eligible_for_shadow": True, "weights": user_weights([])}
        )
        db.add(proposal)
        db.commit()
        proposal_id = proposal.id
    url = f"/api/v1/mcr/{proposal_id}/approve"
    assert client.post(url, headers=headers, json={}).status_code == 403
    proof = client.post("/api/v1/auth/step-up", headers=headers, json={"password": "HelmDemo!2026"}).json()[
        "step_up_token"
    ]
    signed = {**headers, "X-Step-Up": proof}
    assert client.post(url, headers=signed, json={}).status_code == 200
    assert client.post(url, headers=signed, json={}).status_code == 403
    other = login(client, "lead@helm.demo")
    assert client.post(url, headers={**other, "X-Step-Up": proof}, json={}).status_code == 403
    with main.SessionLocal() as db:
        assert (
            len(db.scalars(select(ModelApproval).where(ModelApproval.proposal_id == proposal_id)).all()) == 1
        )
