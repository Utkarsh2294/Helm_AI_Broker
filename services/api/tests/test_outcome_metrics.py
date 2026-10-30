from test_plan_ratings import ranked


def test_outcome_metrics_use_current_scoped_ratings_and_do_not_invent_ipt_liability(client):
    url, headers, ranking = ranked(client)
    pid = ranking["top"][0]["plan"]["id"]
    for stars in (2, 4):
        assert (
            client.post(
                url + "/plans/" + pid + "/rating",
                headers=headers,
                json={
                    "ranking_id": ranking["id"],
                    "stars": stars,
                    "decision": "YES",
                    "reason_text": "Fictional plan reviewed against the recorded requirements.",
                },
            ).status_code
            == 200
        )
    data = client.get("/api/v1/insights/outcomes").json()
    assert data["ratings"]["total"] == 1 and data["ratings"]["stars"]["4"] == 1
    assert data["ratings"]["stars"]["2"] == 0
    assert data["bound_ipt_pence"] == 0 and data["bound_cases"] == 0
    assert data["mean_review_seconds"] is None
    assert data["ndcg_series"] == [] and data["cohorts"] == []
    from app import main
    from app.db.store import save_snapshot

    with main.SessionLocal() as db:
        save_snapshot(
            db,
            url.rsplit("/", 1)[-1],
            "selection",
            {
                "ranking_id": ranking["id"],
                "selected": [row["plan"]["id"] for row in ranking["top"][:3]],
                "survey": {"thumbs": {pid: "up"}},
            },
        )
        db.commit()
    measured = client.get("/api/v1/insights/outcomes").json()
    assert measured["ndcg_series"][0]["ndcg3"] == 1
    assert all(row["suppressed"] and row["ndcg3"] is None for row in measured["cohorts"])
