"""Commission diagnostics are separate from suitability scoring."""
import math
from statistics import mean


def ranks(values):
    result = []
    for value in values:
        less = sum(other < value for other in values)
        equal = sum(other == value for other in values)
        result.append(less + (equal + 1) / 2)
    return result


def commission_deviation_check(rows, selected_ids, threshold=2.0):
    if not rows or not selected_ids:
        return {"flag": None, "spearman_rho": 0, "deviation_pct": 0, "requires_audit": False}
    commission = [r["plan"]["commissionPct"] for r in rows]
    engine_ranks = list(range(1, len(rows) + 1))
    commission_ranks = ranks([-value for value in commission])
    left_mean, right_mean = mean(engine_ranks), mean(commission_ranks)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(engine_ranks, commission_ranks))
    denominator = math.sqrt(sum((a - left_mean) ** 2 for a in engine_ranks) * sum((b - right_mean) ** 2 for b in commission_ranks))
    chosen = [r["plan"]["commissionPct"] for r in rows if r["plan"]["id"] in selected_ids]
    delta = mean(chosen) - mean(commission[:min(3, len(rows))])
    return {"flag": "commission_deviation" if delta > threshold else None, "deviation_pct": delta,
            "spearman_rho": numerator / denominator if denominator else 0,
            "requires_audit": delta > threshold}
