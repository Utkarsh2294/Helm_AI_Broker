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
