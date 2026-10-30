"""Behavioural invariants the engine must always satisfy (Python port)."""
import unittest

from helm_engine import engine as E

CTX = {
    "budgetAnnualPence": 90000, "bench": {"p10": 50000, "p90": 160000}, "iptRate": 0.12,
    "desiredCoverage": {
        "cancer": {"level": 3, "importance": 1, "mustHave": True},
        "mental": {"level": 2, "importance": 0.6},
        "outpatient": {"level": 3, "importance": 0.8},
    },
    "desiredHospitalLevel": 2, "preferredUnderwriting": "moratorium", "maxSeverity": 10,
}


def mk(pid, insurer, base, **over):
    p = {
        "id": pid, "insurerId": insurer, "status": "quoted", "basePremiumPence": base,
        "annualPremiumPence": E._js_round(base * 1.12), "excessPence": 25000,
        "coverage": {"cancer": 3, "mental": 2, "outpatient": 3}, "hospitalListLevel": 2,
        "preferredHospitalShare": 0.7, "exclusionSeverities": [], "underwritingType": "moratorium",
        "insurerStats": {"n": 200, "upheldRate": 0.2, "finStrength": 0.8, "slaScore": 0.7},
        "docsRequired": 4, "docsUnavailable": 0, "turnaroundDays": 3, "ipidCompleteness": 0.9,
        "plainLanguage": 0.8, "exclusionsCount": 8, "commissionPct": 15,
    }
    p.update(over)
    return p


PLANS = [
    mk("A1", "A", 70000),
    mk("A2", "A", 85000, coverage={"cancer": 3, "mental": 3, "outpatient": 3}, hospitalListLevel=3),
    mk("A3", "A", 60000, coverage={"cancer": 2, "mental": 1, "outpatient": 1}),
    mk("B1", "B", 78000, underwritingType="fmu", exclusionSeverities=[3, 2]),
    mk("C1", "C", 95000, hospitalListLevel=3, preferredHospitalShare=0.95,
       insurerStats={"n": 40, "upheldRate": 0.1, "finStrength": 0.9, "slaScore": 0.9}),
    mk("D1", "D", 66000, docsRequired=5, docsUnavailable=3, turnaroundDays=12, ipidCompleteness=0.5),
    mk("E1", "E", 72000, annualPremiumPence=99999),
]
W = E.user_weights(["affordability", "coverage", "network"])


class Invariants(unittest.TestCase):
    def test_roc_textbook(self):
        w = E.roc_weights(3)
        for got, exp in zip(w, [0.6111, 0.2778, 0.1111]):
            self.assertAlmostEqual(got, exp, places=3)

    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(W.values()), 1.0, places=9)

    def test_gates(self):
        extra = mk("X", "X", 70000, coverage={"cancer": 1, "mental": 2, "outpatient": 3})
        r = E.rank_plans(PLANS + [extra], CTX, W)
        ex = {e["id"]: e for e in r["excluded"]}
        self.assertIn("must_have_missing:cancer", ex["X"]["reasons"])
        self.assertTrue(ex["E1"]["needsHuman"])
        self.assertNotIn("E1", [x["id"] for x in r["rows"]])

    def test_medical_ambiguity_routes_to_human_not_scored(self):
        r = E.rank_plans([mk("M", "A", 70000, medicalFlagsAmbiguous=True)], CTX, W)
        self.assertEqual(r["rows"], [])
        self.assertTrue(r["excluded"][0]["needsHuman"])

    def test_scores_bounded_and_points_sum_to_fit(self):
        for r in E.rank_plans(PLANS, CTX, W)["rows"]:
            self.assertTrue(0 <= r["score"] <= 100)
            self.assertAlmostEqual(sum(r["points"].values()), r["fit"], delta=0.05)

    def test_cheaper_never_lowers_score(self):
        a = E.rank_plans([mk("P", "A", 80000)], CTX, W)["rows"][0]["score"]
        b = E.rank_plans([mk("P", "A", 70000)], CTX, W)["rows"][0]["score"]
        self.assertGreater(b, a)

    def test_no_rank_reversal(self):
        full = E.rank_plans(PLANS, CTX, W)["rows"]
        ids = [r["id"] for r in full]
        score = {r["id"]: r["score"] for r in full}
        for drop in ids:
            sub = E.rank_plans([p for p in PLANS if p["id"] != drop], CTX, W)["rows"]
            self.assertEqual([r["id"] for r in sub], [i for i in ids if i != drop])
            for r in sub:
                self.assertEqual(r["score"], score[r["id"]])

    def test_commission_blind(self):
        a = [r["score"] for r in E.rank_plans(PLANS, CTX, W)["rows"]]
        b = [r["score"] for r in E.rank_plans([{**p, "commissionPct": 40} for p in PLANS], CTX, W)["rows"]]
        self.assertEqual(a, b)

    def test_deterministic(self):
        self.assertEqual(E.rank_plans(PLANS, CTX, W), E.rank_plans(PLANS, CTX, W))

    def test_monte_carlo_consistent(self):
        rows = E.rank_plans(PLANS, CTX, W)["rows"]
        a = E.mc_stability(rows, W, seed=1)
        self.assertEqual(a, E.mc_stability(rows, W, seed=1))
        self.assertAlmostEqual(sum(x["pTop1"] for x in a.values()), 1.0, places=9)

    def test_diversity(self):
        rows = E.rank_plans(PLANS, CTX, W)["rows"]
        s = E.diversify(rows, 5, 2)
        self.assertEqual(len(s), 5)
        cnt = {}
        for r in s:
            cnt[r["insurerId"]] = cnt.get(r["insurerId"], 0) + 1
        self.assertTrue(all(c <= 2 for c in cnt.values()))

    def test_learning_bounded(self):
        rows = E.rank_plans(PLANS, CTX, W)["rows"]
        hi = max(rows, key=lambda r: r["u"]["network"])
        lo = min(rows, key=lambda r: r["u"]["network"])
        comps = [{"better": hi["u"], "worse": lo["u"]}] * 60
        learned = E.learn_weights(W, comps)
        self.assertGreater(learned["network"], W["network"])
        self.assertAlmostEqual(sum(learned.values()), 1.0, places=9)
        shr = E.shrink_learned(W, learned, 10)
        self.assertLess(abs(shr["network"] - W["network"]), abs(learned["network"] - W["network"]))
        final = E.combine_weights(W, shr)
        for c in E.CRITERIA:
            lo_b = max(0.02, W[c] * 0.7)
            self.assertTrue(lo_b - 1e-9 <= final[c] <= max(lo_b, W[c] * 1.3) + 1e-9)

    def test_ndcg(self):
        self.assertEqual(E.ndcg_at_k(list("abcd"), list("abc"), 3), 1)
        self.assertLess(E.ndcg_at_k(list("dabc"), list("abc"), 3), 1)

    def test_worked_example_matches_js_run(self):
        """Numbers printed by the verified JS run (see plan Section 7.8)."""
        r = E.rank_plans(PLANS, CTX, W)
        got = [(x["id"], round(x["score"], 1)) for x in r["rows"]]
        self.assertEqual(got, [("A1", 77.1), ("D1", 76.8), ("B1", 69.2), ("A2", 65.9), ("C1", 61.1)])
        self.assertEqual(sorted(e["id"] for e in r["excluded"]), ["A3", "E1"])


if __name__ == "__main__":
    unittest.main()
