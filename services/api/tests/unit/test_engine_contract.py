import json
import random
import subprocess
from collections import Counter
from decimal import Decimal
import pytest
from app.config import ROOT
from app.engine.ranking import aggregate, combine_weights, gate, rank_plans, user_weights, utilities
from app.engine.governance import commission_deviation_check
from app.agents.quotation import build_rfq, premium_with_tax, simulate_responses
from app.schemas import CRITERIA
from test_quotation import fixture_dnr


@pytest.fixture
def sample():
    dnr = fixture_dnr()
    quotes, _ = simulate_responses(build_rfq(dnr, signed_off=True))
    return dnr.needs, quotes


@pytest.mark.parametrize("m", range(8))
def test_roc_mass_and_rank_order(m):
    w = user_weights(list(CRITERIA[:m]))
    assert abs(sum(w.values()) - 1) < 1e-12
    assert all(w[CRITERIA[i]] > w[CRITERIA[i + 1]] for i in range(m - 1))


def test_roc_known_values():
    w = user_weights(["affordability", "coverage", "network"])
    assert w["affordability"] == pytest.approx(0.5194444444444444)
    assert w["coverage"] == pytest.approx(0.2361111111111111)


def test_bisection_thousand_extreme_proposals():
    rng = random.Random(9)
    for _ in range(1000):
        base = user_weights(rng.sample(list(CRITERIA), rng.randrange(8)))
        learned = {c: rng.random() ** 12 for c in CRITERIA}
        final = combine_weights(base, learned)
        assert abs(sum(final.values()) - 1) < 1e-10
        assert all(max(0.02, base[c] * 0.7) - 1e-10 <= final[c] <= base[c] * 1.3 + 1e-10 for c in CRITERIA)


def test_all_thirty_drop_one_no_rank_reversal(sample):
    needs, plans = sample
    baseline = rank_plans(plans, needs, "fixed", draws=0)["all"]
    ids = [r["plan"]["id"] for r in baseline]
    for omitted in plans:
        result = rank_plans([p for p in plans if p.id != omitted.id], needs, "fixed", draws=0)
        assert [r["plan"]["id"] for r in result["all"]] == [p for p in ids if p != omitted.id]


def test_independent_javascript_scalar_parity_forty_cases(sample):
    needs, plans = sample
    rng = random.Random(81)
    cases = []
    for i in range(40):
        p = plans[i % len(plans)].model_copy(deep=True)
        p.excessPence = rng.randrange(100001)
        p.insurerStats.finStrength = rng.random()
        cases.append(
            {
                "plan": p.model_dump(),
                "needs": needs.model_dump(),
                "weights": user_weights(rng.sample(list(CRITERIA), 3)),
            }
        )
    result = subprocess.run(
        ["node", str(ROOT / "tools/engine_oracle.mjs")],
        input=json.dumps(cases),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    from app.schemas import Plan, Needs

    for case, oracle in zip(cases, json.loads(result.stdout)):
        u = utilities(Plan.model_validate(case["plan"]), Needs.model_validate(case["needs"]))
        assert all(abs(u[c] - oracle["utilities"][c]) < 1e-9 for c in CRITERIA)
        assert abs(aggregate(u, case["weights"])[0] - oracle["score"]) < 1e-9


def test_monotonicity_and_diversity(sample):
    needs, plans = sample
    lower = plans[0].model_copy(deep=True)
    lower.basePremiumPence -= 1000
    lower.annualPremiumPence = premium_with_tax(lower.basePremiumPence)
    assert (
        aggregate(utilities(lower, needs), user_weights([]))[0]
        >= aggregate(utilities(plans[0], needs), user_weights([]))[0]
    )
    result = rank_plans(plans, needs, "diversity", draws=50)
    assert max(Counter(r["plan"]["insurerId"] for r in result["top"]).values()) <= 2


@pytest.mark.parametrize("seed", range(10))
def test_seeded_uncertainty_and_points(sample, seed):
    needs, plans = sample
    result = rank_plans(plans, needs, str(seed), draws=30)
    assert result == rank_plans(plans, needs, str(seed), draws=30)
    for row in result["all"]:
        assert 0 <= row["score"] <= 100
        assert sum(row["points"].values()) == pytest.approx(row["fit"])


def test_commission_diagnostic_cannot_change_scores(sample):
    needs, plans = sample
    first = rank_plans(plans, needs, "comm", draws=0)
    for p in plans:
        p.commissionPct = 99
    second = rank_plans(plans, needs, "comm", draws=0)
    assert [r["score"] for r in first["all"]] == [r["score"] for r in second["all"]]
    rows = first["top"]
    rows[-1]["plan"]["commissionPct"] = 90
    assert commission_deviation_check(rows, [r["plan"]["id"] for r in rows[-3:]])["requires_audit"]


def test_hard_gate_tolerance_and_zero_importance(sample):
    needs, plans = sample
    p = plans[0].model_copy(deep=True)
    p.annualPremiumPence += 1
    assert gate(p, needs, Decimal("0.12"))[0] is None
    p.annualPremiumPence += 1
    assert gate(p, needs, Decimal("0.12"))[0] == "human"
    for desired in needs.coverage.values():
        desired.importance = 0
    assert utilities(plans[0], needs)["coverage"] == 0.5
