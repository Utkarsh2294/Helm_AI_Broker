import random
from app.agents.quotation import build_rfq, simulate_responses
from app.engine.ranking import combine_weights, rank_plans, user_weights
from app.schemas import CRITERIA
from test_quotation import fixture_dnr


def test_weights_caps_after_normalisation():
    rng = random.Random(42)
    for m in range(8):
        base = user_weights(list(CRITERIA[:m]))
        for _ in range(10):
            w = combine_weights(base, {c: rng.random() ** 5 for c in CRITERIA})
            assert abs(sum(w.values()) - 1) < 1e-12
            assert all(max(0.02, 0.7 * base[c]) - 1e-12 <= w[c] <= 1.3 * base[c] + 1e-12 for c in CRITERIA)


def test_ranking_deterministic_neutral_and_no_reversal():
    dnr = fixture_dnr()
    plans, _ = simulate_responses(build_rfq(dnr, signed_off=True))
    result = rank_plans(plans, dnr.needs, "seed", draws=100)
    assert result == rank_plans(plans, dnr.needs, "seed", draws=100)
    scores = {r["plan"]["id"]: r["score"] for r in result["all"]}
    for omitted in plans:
        batch = [p.model_copy(update={"commissionPct": 99}) for p in plans if p.id != omitted.id]
        rows = rank_plans(batch, dnr.needs, "seed", draws=0)["all"]
        assert all(scores[r["plan"]["id"]] == r["score"] for r in rows)
    assert len(result["top"]) == 5
    for row in result["top"]:
        assert 0 <= row["score"] <= 100
        assert abs(sum(row["points"].values()) - row["fit"]) < 1e-10


def test_hard_gates_and_human_referral():
    dnr = fixture_dnr()
    plans, _ = simulate_responses(build_rfq(dnr, signed_off=True))
    plans[0].medicalFlagsAmbiguous = True
    plans[1].annualPremiumPence += 500
    plans[2].coverage["cancer"] = 0
    result = rank_plans(plans, dnr.needs, "gate", draws=0)
    assert len(result["needs_human"]) == 2
    assert result["excluded"][0]["reasons"] == ["must_have_missing:cancer"]
