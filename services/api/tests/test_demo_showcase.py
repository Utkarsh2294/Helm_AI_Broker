from sqlalchemy import select
from app import main
from app.db.models import Case, User, Approval, Publication
from app.db.store import save_snapshot, audit
from test_governance_access import login


def test_demo_showcase_requires_actual_case_publication_and_independent_verified_reviewers(client):
    headers = login(client, "broker@helm.demo")
    data = client.post("/api/v1/demo/showcase", headers=headers).json()
    assert data["case_state"] == "FACTFIND_REVIEW" and not data["demo_ready"]
    assert client.post("/api/v1/demo/showcase", headers=headers).json()["case_id"] == data["case_id"]
    headers = login(client, "compliance@helm.demo")

    def review(headers):
        current = client.get("/api/v1/demo/showcase").json()
        proof = client.post(
            "/api/v1/auth/step-up", headers=headers, json={"password": "HelmDemo!2026"}
        ).json()["step_up_token"]
        return client.post(
            "/api/v1/demo/showcase/reviews",
            headers={**headers, "X-Step-Up": proof},
            json={
                "review_hash": current["review_hash"],
                "document_ids": [d["id"] for d in current["documents"]],
                "acknowledgements": list(current["checklist"]),
                "note": "I reviewed the fictional workflow and its explicit limitations.",
            },
        )

    assert review(headers).status_code == 409
    # Isolate review gating with a held G2/publication fixture. Full workflow is exercised in browser tests.
    with main.SessionLocal() as db:
        case = db.get(Case, data["case_id"])
        case.state = "PUBLISHED"
        broker = db.scalar(select(User).where(User.email == "broker@helm.demo"))
        pack_hash = "f" * 64
        save_snapshot(db, case.id, "pack", {"pack_hash": pack_hash})
        approval = Approval(case_id=case.id, gate="G2", user_id=broker.id, payload_hash=pack_hash)
        db.add(approval)
        db.flush()
        db.add(Publication(case_id=case.id, approval_id=approval.id, pack_hash=pack_hash))
        audit(db, case.id, "demo_publication_fixture", "system", {"fictional": True})
        db.commit()
    assert review(headers).json()["demo_ready"] is False
    assert review(headers).status_code == 409
    legal = login(client, "legal@helm.demo")
    result = review(legal)
    assert result.status_code == 200, result.text
    assert result.json()["demo_ready"] and not result.json()["live_release_approved"]
    assert {r["role"] for r in result.json()["reviews"]} == {"compliance_officer", "legal_reviewer"}
    import pymupdf

    pdf = client.get("/api/v1/demo/showcase/report.pdf")
    assert pdf.status_code == 200
    with pymupdf.open(stream=pdf.content, filetype="pdf") as document:
        text = " ".join(page.get_text() for page in document)
        assert "LIVE RELEASE APPROVED: FALSE" in text and "Casey Demo" in text
        assert result.json()["manifest_hash"] in text
    assert (
        client.post("/api/v1/cases/" + data["case_id"] + "/approve", headers=legal, json={}).status_code
        == 403
    )
