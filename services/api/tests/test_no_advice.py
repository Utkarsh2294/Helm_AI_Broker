from sqlalchemy import select
from app import main
from app.db.models import Job, Publication, Approval
from test_plan_ratings import ranked


def test_all_excluded_closes_without_publication_and_requires_current_complete_assessments(client):
    url, headers, ranking = ranked(client)
    body = {
        "ranking_id": ranking["id"],
        "reason": "No fictional plan fits the recorded needs after review.",
        "confirmed": True,
    }
    assert client.post(url + "/close-without-advice", headers=headers, json=body).status_code == 422
    for row in ranking["top"]:
        response = client.post(
            url + "/plans/" + row["plan"]["id"] + "/rating",
            headers=headers,
            json={"ranking_id": ranking["id"], "stars": 1, "decision": "NO", "reason_text": body["reason"]},
        )
        assert response.status_code == 200
    assert (
        client.post(
            url + "/close-without-advice", headers=headers, json={**body, "ranking_id": "stale"}
        ).status_code
        == 409
    )
    assert (
        client.post(
            url + "/close-without-advice", headers=headers, json={**body, "confirmed": False}
        ).status_code
        == 422
    )
    result = client.post(url + "/close-without-advice", headers=headers, json=body)
    assert result.status_code == 200 and result.json() == {"state": "CLOSED", "recommendation_sent": False}
    case = client.get(url).json()
    assert body["reason"] not in str(case["events"])
    assert any(e["type"] == "no_suitable_plans" for e in case["events"])
    with main.SessionLocal() as db:
        case_id = url.rsplit("/", 1)[-1]
        assert not db.scalar(select(Publication).where(Publication.case_id == case_id))
        assert not db.scalar(select(Approval).where(Approval.case_id == case_id, Approval.gate == "G2"))
        assert not db.scalar(select(Job).where(Job.case_id == case_id, Job.status == "pending"))
    assert client.post(url + "/close-without-advice", headers=headers, json=body).status_code == 409


def test_recommend_or_referral_cannot_be_converted_to_no_advice_closure(client):
    url, headers, ranking = ranked(client)
    for i, row in enumerate(ranking["top"]):
        assert (
            client.post(
                url + "/plans/" + row["plan"]["id"] + "/rating",
                headers=headers,
                json={
                    "ranking_id": ranking["id"],
                    "stars": 3,
                    "decision": "REFER" if i == 0 else "NO",
                    "reason_text": "Underwriter review is still required for this fictional plan.",
                },
            ).status_code
            == 200
        )
    assert (
        client.post(
            url + "/close-without-advice",
            headers=headers,
            json={
                "ranking_id": ranking["id"],
                "reason": "Closing with a referral outstanding must be blocked.",
                "confirmed": True,
            },
        ).status_code
        == 422
    )
