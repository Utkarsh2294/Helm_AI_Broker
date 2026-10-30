from test_plan_ratings import ranked
from app.config import settings


def test_referral_requires_saved_human_decision_and_cannot_create_cover_terms(client, monkeypatch):
    url, headers, ranking = ranked(client)
    pid = ranking["top"][0]["plan"]["id"]
    body = {
        "ranking_id": ranking["id"],
        "plan_ids": [pid],
        "reason": "Please ask the underwriter to clarify the supplied terms.",
    }
    assert client.post(url + "/referrals", headers=headers, json=body).status_code == 422
    assert (
        client.post(
            url + "/plans/" + pid + "/rating",
            headers=headers,
            json={
                "ranking_id": ranking["id"],
                "stars": 3,
                "decision": "REFER",
                "reason_text": body["reason"],
            },
        ).status_code
        == 200
    )
    response = client.post(url + "/referrals", headers=headers, json=body)
    assert response.status_code == 200 and response.json()["state"] == "UW_REFERRAL"
    assert not response.json()["external_message_sent"]
    assert client.post(url + "/selection", headers=headers, json={}).status_code in (409, 422)
    resolution = {
        "referral_hash": response.json()["referral_hash"],
        "underwriter_reference": "DEMO-UW-001",
        "reason": "Fictional underwriter confirmed that a broker must review the original terms.",
        "fictional_confirmation": True,
    }
    monkeypatch.setattr(settings(), "clock_mode", "live")
    assert client.post(url + "/referrals/resolve", headers=headers, json=resolution).status_code == 403
    monkeypatch.setattr(settings(), "clock_mode", "demo")
    result = client.post(url + "/referrals/resolve", headers=headers, json=resolution)
    assert result.status_code == 200 and result.json()["reassess_plans_required"]
    current = client.get(url).json()
    assert current["ranking"]["id"] == ranking["id"] and current["state"] == "BROKER_REVIEW"
    assert body["reason"] not in str(current["events"])
    assert current["broker_referral"]["reason"] == "[REDACTED]"
