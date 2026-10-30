from sqlalchemy import select
import pytest
from app import main
from app.db.models import Job, utcnow
from app.db.platform import BrokerRating
from app.plan_ratings import edit_distance


def ranked(client):
    login = client.post(
        "/api/v1/auth/password", json={"email": "broker@helm.demo", "password": "HelmDemo!2026"}
    ).json()
    headers = {"X-CSRF-Token": login["csrf"]}
    case = client.post(
        "/api/v1/demo/requests",
        headers=headers,
        json={
            "id": "ratings-case",
            "name": "Fictional reviewer",
            "needs": {"coverage": {"outpatient": {"level": 2}}},
        },
    ).json()
    url = "/api/v1/cases/" + case["id"]
    assert client.post(url + "/sign-off", headers=headers, json={"dnr_acknowledged": True}).status_code == 200
    assert client.post(url + "/release", headers=headers, json={}).status_code == 200
    with main.SessionLocal() as db:
        job = db.scalar(select(Job).where(Job.case_id == case["id"], Job.kind == "collect_quotes"))
        job.due_at = utcnow().isoformat()
        db.commit()
    return url, headers, client.get(url).json()["ranking"]


def test_all_reviews_are_required_and_are_immutable_ranking_bound_encrypted_and_server_compared(client):
    url, headers, ranking = ranked(client)
    ids = [row["plan"]["id"] for row in ranking["top"]]
    selection = {
        "ranking_id": ranking["id"],
        "selected": ids[:3],
        "survey": {"thumbs": dict.fromkeys(ids[:3], "up")},
        "acknowledgements": ids[:3],
    }
    blocked = client.post(url + "/selection", headers=headers, json=selection)
    assert blocked.status_code == 422 and blocked.json()["error"] == "UNRATED_PLANS"
    assert client.post(url + "/approve", headers=headers, json={}).status_code in (409, 422)
    first = ranking["top"][0]
    body = {
        "ranking_id": ranking["id"],
        "stars": 4,
        "decision": "YES",
        "reason_text": first["ai_draft_text"],
        "ai_draft_text": "forged draft",
    }
    response = client.post(url + "/plans/" + ids[0] + "/rating", headers=headers, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["is_edited"] is False and response.json()["chars_changed"] == 0
    for invalid in (
        {"stars": 0},
        {"stars": True},
        {"reason_text": " " * 30},
        {"decision": "MAYBE"},
        {"ranking_id": "obsolete"},
    ):
        assert client.post(
            url + "/plans/" + ids[0] + "/rating", headers=headers, json={**body, **invalid}
        ).status_code in (409, 422)
    reason = "Recorded needs, excess and hospital preference reviewed. This trade-off is appropriate for the fictional fixture."
    for plan_id in ids:
        response = client.post(
            url + "/plans/" + plan_id + "/rating", headers=headers, json={**body, "reason_text": reason}
        )
        assert response.status_code == 200, response.text
        assert response.json()["is_edited"]
    saved = client.get(url + "/ratings").json()
    assert len(saved["ratings"]) == 5
    assert next(row for row in saved["ratings"] if row["plan_id"] == ids[0])["version"] == 2
    with main.SessionLocal() as db:
        rows = db.scalars(select(BrokerRating)).all()
        assert len(rows) == 6
        assert reason not in str(
            db.connection().exec_driver_sql("SELECT body FROM broker_ratings").fetchall()
        )
        rows[0].stars = 1
        with pytest.raises(ValueError, match="append-only"):
            db.flush()
        db.rollback()
    current = client.get(url).json()
    assert reason not in str(current["events"])
    packed = client.post(url + "/selection", headers=headers, json=selection)
    assert packed.status_code == 200, packed.text
    assert len(packed.json()["pack"]["broker_ratings"]) == 5
    assert packed.json()["pack"]["ratings_hash"]
    assert client.post(url + "/plans/" + ids[0] + "/rating", headers=headers, json=body).status_code == 409


def test_excluded_or_referred_plans_cannot_be_selected_and_other_brokers_do_not_inherit_ratings(client):
    url, headers, ranking = ranked(client)
    ids = [row["plan"]["id"] for row in ranking["top"]]
    for plan_id in ids:
        response = client.post(
            url + "/plans/" + plan_id + "/rating",
            headers=headers,
            json={
                "ranking_id": ranking["id"],
                "stars": 3,
                "decision": "NO" if plan_id == ids[0] else "YES",
                "reason_text": "Fictional reviewed assessment against coverage, cost and availability.",
            },
        )
        assert response.status_code == 200
    result = client.post(
        url + "/selection",
        headers=headers,
        json={
            "ranking_id": ranking["id"],
            "selected": ids[:3],
            "survey": {"thumbs": dict.fromkeys(ids[:3], "up")},
            "acknowledgements": ids[:3],
        },
    )
    assert result.status_code == 422 and result.json()["error"] == "PLAN_DECISION_CONFLICT"
    client.post("/api/v1/auth/password", json={"email": "lead@helm.demo", "password": "HelmDemo!2026"})
    assert client.get(url + "/ratings").json()["ratings"] == []


def test_edit_distance_is_symmetric_and_counts_insert_delete_replace():
    assert edit_distance("kitten", "sitting") == 3
    assert edit_distance("", "abc") == edit_distance("abc", "") == 3


def test_g2_binds_every_review_and_suitability_confirmation_to_fresh_one_use_proof(client):
    url, headers, ranking = ranked(client)
    ids = [row["plan"]["id"] for row in ranking["top"]]
    for plan_id in ids:
        assert (
            client.post(
                url + "/plans/" + plan_id + "/rating",
                headers=headers,
                json={
                    "ranking_id": ranking["id"],
                    "stars": 4,
                    "decision": "YES",
                    "reason_text": "Checked this fictional plan against the needs, annual cost and recorded coverage.",
                },
            ).status_code
            == 200
        )
    case = client.post(
        url + "/selection",
        headers=headers,
        json={
            "ranking_id": ranking["id"],
            "selected": ids[:3],
            "survey": {"thumbs": dict.fromkeys(ids[:3], "up")},
            "acknowledgements": ids[:3],
        },
    ).json()
    assert (
        client.post(
            url + "/publish", headers=headers, json={"pack_hash": case["pack"]["pack_hash"]}
        ).status_code
        == 403
    )
    failed = client.post("/api/v1/auth/step-up", headers=headers, json={"password": "wrong-password"})
    assert failed.status_code in (401, 403)
    proof = client.post("/api/v1/auth/step-up", headers=headers, json={"password": "HelmDemo!2026"}).json()[
        "step_up_token"
    ]
    unconfirmed = client.post(
        url + "/publish",
        headers=headers,
        json={"pack_hash": case["pack"]["pack_hash"], "step_up_token": proof},
    )
    assert unconfirmed.status_code == 422 and unconfirmed.json()["error"] == "SUITABILITY_NOT_CONFIRMED"
    pack = case["pack"]
    case = client.put(
        url + "/suitability",
        headers=headers,
        json={
            "text": pack["suitability_final"],
            "dnr_sections_confirmed": ["priorities", "coverage", "budget", "household", "medical_flag"],
            "unmet_needs_addressed": [f"{n['plan_id']}:{n['need']}" for n in pack["unmet_needs"]],
            "suitability_confirmed_plans": ids[:3],
            "overall_suitability_confirmed": True,
        },
    ).json()
    body = {"pack_hash": case["pack"]["pack_hash"], "step_up_token": proof}
    assert client.post(url + "/publish", headers=headers, json=body).status_code == 200
    assert client.post(url + "/publish", headers=headers, json=body).status_code in (403, 409)
    events = client.get(url).json()["events"]
    approval = next(e for e in events if e["type"] == "G2_APPROVED")
    assert len(approval["payload"]["step_up_token_hash"]) == 64
    assert proof not in str(events)
