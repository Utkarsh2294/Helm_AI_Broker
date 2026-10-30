"""Parity: Python engine must reproduce the verified JS reference on golden vectors."""
import json
import math
import os
import unittest

from helm_engine import engine as E

HERE = os.path.dirname(os.path.abspath(__file__))
VEC = os.path.join(HERE, "..", "js", "vectors.json")
TOL = 1e-9


def close(a, b, path, tol=TOL):
    if isinstance(b, dict):
        assert set(a) == set(b), f"{path}: keys {sorted(a)} != {sorted(b)}"
        for k in b:
            close(a[k], b[k], f"{path}.{k}", tol)
    elif isinstance(b, list):
        assert len(a) == len(b), f"{path}: len {len(a)} != {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            close(x, y, f"{path}[{i}]", tol)
    elif isinstance(b, (int, float)) and not isinstance(b, bool):
        assert abs(a - b) <= tol * max(1, abs(b)), f"{path}: {a} != {b}"
    else:
        assert a == b, f"{path}: {a!r} != {b!r}"


class Parity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(VEC) as f:
            cls.v = json.load(f)

    def test_roc(self):
        for m, expected in zip([1, 2, 3, 5, 7], self.v["roc"]):
            close(E.roc_weights(m), expected, f"roc{m}")

    def test_weights_rank_gate_utilities(self):
        for i, sc in enumerate(self.v["scenarios"]):
            w = E.user_weights(sc["order"])
            close(w, sc["weights"], f"s{i}.weights")
            got = E.rank_plans(sc["plans"], sc["ctx"], w)
            exp = sc["ranked"]
            self.assertEqual([r["id"] for r in got["rows"]], [r["id"] for r in exp["rows"]], f"s{i} order")
            # points are rounded to 2dp (toFixed vs round): allow 0.011
            for gr, er in zip(got["rows"], exp["rows"]):
                close(gr["points"], er["points"], f"s{i}.{gr['id']}.points", tol=0.011)
                gr2 = {k: v for k, v in gr.items() if k != "points"}
                er2 = {k: v for k, v in er.items() if k != "points"}
                close(gr2, er2, f"s{i}.{gr['id']}")
            close(got["excluded"], exp["excluded"], f"s{i}.excluded")
            self.assertEqual([r["id"] for r in E.diversify(got["rows"], 5, 2)], sc["diversified"], f"s{i} diversify")

    def test_monte_carlo_flip_learning_combine_ndcg(self):
        n = 0
        for i, sc in enumerate(self.v["scenarios"]):
            if "mc" not in sc:
                continue
            n += 1
            w = sc["weights"]
            rows = sc["ranked"]["rows"]
            close(E.mc_stability(rows, w, draws=300, seed=11 + i), sc["mc"], f"s{i}.mc")
            close(E.flip_analysis(rows[0], rows[1], w), sc["flip"], f"s{i}.flip")
            learned = E.learn_weights(w, sc["comps"])
            close(learned, sc["learned"], f"s{i}.learned")
            shrunk = E.shrink_learned(w, learned, len(sc["comps"]))
            close(shrunk, sc["shrunk"], f"s{i}.shrunk")
            close(E.combine_weights(w, shrunk), sc["combined"], f"s{i}.combined")
            extreme = {c: (0.95 if q == 0 else 0.05 / 6) for q, c in enumerate(E.CRITERIA)}
            comb = E.combine_weights(w, extreme)
            close(comb, sc["combinedExtreme"], f"s{i}.combinedExtreme")
            ids = [r["id"] for r in rows]
            close(E.ndcg_at_k(ids, list(reversed(ids[:3])), 3), sc["ndcg"], f"s{i}.ndcg")
            close(E.ndcg_at_k(ids, ids[2:5], 3), sc["ndcg2"], f"s{i}.ndcg2")
        self.assertGreater(n, 25)

    def test_cap_holds_after_normalisation(self):
        for i, sc in enumerate(self.v["scenarios"]):
            w = sc["weights"]
            extreme = {c: (0.95 if q == 0 else 0.05 / 6) for q, c in enumerate(E.CRITERIA)}
            out = E.combine_weights(w, extreme)
            self.assertAlmostEqual(sum(out.values()), 1.0, places=9)
            for c in E.CRITERIA:
                lo = max(0.02, w[c] * 0.7)
                hi = max(lo, w[c] * 1.3)
                self.assertTrue(lo - 1e-9 <= out[c] <= hi + 1e-9, f"s{i} {c}: {w[c]} -> {out[c]}")


if __name__ == "__main__":
    unittest.main()
