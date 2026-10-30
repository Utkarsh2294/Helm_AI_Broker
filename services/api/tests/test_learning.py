from app.agents.learning import propose_improvement
from app.engine.ranking import user_weights
from app.schemas import CRITERIA


def records():
    rows = [{"plan": {"id": str(i)}, "utilities": {c: (i + 1) / 6 for c in CRITERIA}} for i in range(5)]
    return [
        {
            "id": f"s{i}",
            "case_id": f"c{i}",
            "ranking": {"top": rows},
            "selected": ["4", "3", "2"],
            "survey": {"thumbs": {"4": "up", "3": "up", "2": "up"}},
        }
        for i in range(10)
    ]


def test_learning_has_evidence_gate_holdout_and_no_auto_activation():
    assert propose_improvement([])["status"] == "insufficient_evidence"
    data = records()
    data[0]["survey"]["thumbs"]["4"] = "down"
    base = user_weights([])
    proposal = propose_improvement(data, base)
    assert proposal["status"] == "no_improvement" and not proposal["auto_applied"]
    assert proposal["disputed"] == ["s0"]
    assert len(proposal["holdout_case_ids"]) >= 1
    assert all(0.7 * base[c] <= proposal["weights"][c] <= 1.3 * base[c] for c in CRITERIA)
    assert abs(sum(proposal["weights"].values()) - 1) < 1e-12


def test_detailed_ratings_weight_training_and_referred_plans_are_held_out():
    from app.agents.learning import preference_pairs

    record = records()[0]
    baseline, _ = preference_pairs([record])
    record["broker_ratings"] = [
        {"plan_id": str(i), "stars": 4, "decision": "REFER" if i == 0 else "YES", "is_edited": True}
        for i in range(5)
    ]
    rated, _ = preference_pairs([record])
    assert len(rated) < len(baseline)
    assert all(pair["weight"] in (0.4, 0.8) for pair in rated)
    for rating in record["broker_ratings"]:
        rating["is_edited"] = False
    reduced, _ = preference_pairs([record])
    assert [p["weight"] for p in reduced] == [p["weight"] * 0.5 for p in rated]


def test_small_heldout_improvement_cannot_propose_an_activatable_model(monkeypatch):
    from app.agents import learning

    values = iter(
        [
            {"ndcg3": 0.8, "top3_agreement": 0.8, "cases": 2},
            {"ndcg3": 0.81, "top3_agreement": 0.9, "cases": 2},
        ]
    )
    monkeypatch.setattr(learning, "metrics", lambda *args: next(values))
    result = learning.propose_improvement(records(), user_weights([]))
    assert result["status"] == "no_improvement" and not result["eligible_for_shadow"]
