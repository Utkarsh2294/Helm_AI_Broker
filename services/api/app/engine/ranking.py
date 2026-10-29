"""Fixed-anchor utilities: adding a quote cannot change another quote's score."""
import hashlib
import math
import random
from collections import Counter
from decimal import Decimal

from app.agents.quotation import premium_with_tax
from app.schemas import CRITERIA, Needs, Plan

ENGINE_VERSION = "helm-pmi-0.1"


def clamp(x):
    return min(1.0, max(0.0, x))


def user_weights(priorities: list[str]) -> dict[str, float]:
    if len(set(priorities)) != len(priorities) or set(priorities) - set(CRITERIA):
        raise ValueError("Invalid priorities")
    m = len(priorities)
    if not m:
        return dict.fromkeys(CRITERIA, 1 / len(CRITERIA))
    mass = 1 if m == len(CRITERIA) else 0.85
    weights = dict.fromkeys(CRITERIA, (1 - mass) / max(1, len(CRITERIA) - m))
    weights.update({c: mass * sum(1 / k for k in range(i + 1, m + 1)) / m
                    for i, c in enumerate(priorities)})
    return weights


def combine_weights(base: dict, learned: dict | None = None, blend=0.25) -> dict:
    if not learned:
        return dict(base)
    if not 0 <= blend <= 0.25 or set(learned) != set(CRITERIA):
        raise ValueError("Invalid learned weights or blending coefficient")
    if any(not math.isfinite(v) or v < 0 for v in learned.values()) or sum(learned.values()) <= 0:
        raise ValueError("Learned weights must be nonnegative and finite")
    total = sum(learned.values())
    target = {c: (1 - blend) * base[c] + blend * learned[c] / total for c in CRITERIA}
    lower = {c: max(0.02, base[c] * 0.7) for c in CRITERIA}
    upper = {c: max(lower[c], base[c] * 1.3) for c in CRITERIA}
    lo, hi = -1.0, 1.0
    for _ in range(100):
        shift = (lo + hi) / 2
        if sum(min(upper[c], max(lower[c], target[c] + shift)) for c in CRITERIA) > 1:
            hi = shift
        else:
            lo = shift
    return {c: min(upper[c], max(lower[c], target[c] + (lo + hi) / 2)) for c in CRITERIA}


def utilities(p: Plan, n: Needs) -> dict[str, float]:
    teco = p.annualPremiumPence + 0.25 * min(p.excessPence, 300000)
    exponent = max(-700, min(700, 6 * (teco / n.budget_annual_pence - 1)))
    budget = 1 / (1 + math.exp(exponent))
    reference = clamp((n.reference_high_pence - teco) / (n.reference_high_pence - n.reference_low_pence))
    importance = sum(v.importance for v in n.coverage.values())
    coverage = sum(v.importance * clamp(p.coverage.get(k, 0) / max(v.level, 1))
                   for k, v in n.coverage.items()) / importance if importance else 0.5
    stats = p.insurerStats
    upheld = (stats.n * stats.upheldRate + 30 * 0.25) / (stats.n + 30)
    return {
        "affordability": 0.5 * budget + 0.5 * reference,
        "coverage": coverage,
        "network": 0.6 * clamp(p.hospitalListLevel / n.hospital_level) + 0.4 * p.preferredHospitalShare,
        "underwriting": 0.7 * (1 - clamp(sum(p.exclusionSeverities) / 10)) +
                        0.3 * (1 if p.underwritingType == n.preferred_underwriting else 0.5),
        "insurer_quality": 0.5 * (1 - upheld) + 0.3 * stats.finStrength + 0.2 * stats.slaScore,
        "process_ease": clamp(1 - 0.6 * p.docsUnavailable / max(p.docsRequired, 1) -
                              0.4 * min(p.turnaroundDays / 14, 1)),
        "terms_clarity": clamp(0.5 * p.ipidCompleteness + 0.3 * p.plainLanguage +
                               0.2 * (1 - min(p.exclusionsCount / 20, 1))),
    }


def aggregate(u, w):
    fit = sum(w[c] * u[c] for c in CRITERIA)
    positive = math.sqrt(sum(w[c] * (1 - u[c]) ** 2 for c in CRITERIA))
    negative = math.sqrt(sum(w[c] * u[c] ** 2 for c in CRITERIA))
    balance = negative / (positive + negative) if positive + negative else 0
    return 100 * (0.7 * fit + 0.3 * balance), 100 * fit, 100 * balance


def gate(p: Plan, n: Needs, rate: Decimal) -> tuple[str | None, list[str]]:
    if p.medicalFlagsAmbiguous:
        return "human", ["medical_wording_ambiguous"]
    if abs(p.annualPremiumPence - premium_with_tax(p.basePremiumPence, rate)) > 1:
        return "human", ["premium_arithmetic_mismatch"]
    reasons = []
    if p.status != "quoted":
        reasons.append(p.status)
    if n.hard_budget_cap is not None and p.annualPremiumPence > n.hard_budget_cap:
        reasons.append("hard_budget_exceeded")
    reasons.extend(f"must_have_missing:{k}" for k, v in n.coverage.items()
                   if v.must_have and p.coverage.get(k, 0) < v.level)
    if p.underwritingType not in n.allowed_underwriting:
        reasons.append("underwriting_not_allowed")
    return ("excluded", reasons) if reasons else (None, [])


def diversify(rows):
    counts, chosen = Counter(), []
    for row in rows:
        if counts[row["plan"]["insurerId"]] < 2:
            chosen.append(row)
            counts[row["plan"]["insurerId"]] += 1
        if len(chosen) == 5:
            break
    return chosen


def rank_plans(plans: list[Plan], needs: Needs, ranking_id: str, learned=None,
               tax_rate=Decimal("0.12"), draws=1000) -> dict:
    weights = combine_weights(user_weights(needs.priorities), learned)
    rows, excluded, human = [], [], []
    for p in sorted(plans, key=lambda p: p.id):
        disposition, reasons = gate(p, needs, tax_rate)
        if disposition:
            (human if disposition == "human" else excluded).append({"plan": p.model_dump(), "reasons": reasons})
            continue
        u = utilities(p, needs)
        score, fit, balance = aggregate(u, weights)
        blockers = []
        if p.docsUnavailable / max(p.docsRequired, 1) > 0.5:
            blockers.append("documents_unavailable")
        if p.ipidCompleteness < 0.6:
            blockers.append("incomplete_ipid")
        if p.turnaroundDays > 10:
            blockers.append("slow_turnaround")
        if p.fcaStatus != "authorised":
            blockers.append("fca_status_unverified")
        rows.append({"plan": p.model_dump(), "score": score, "fit": fit, "balance": balance,
                     "utilities": u, "points": {c: 100 * weights[c] * u[c] for c in CRITERIA},
                     "blockers": blockers})
    rows.sort(key=lambda r: (-r["score"], r["plan"]["id"]))
    top = diversify(rows)
    rng = random.Random(int.from_bytes(hashlib.sha256(ranking_id.encode()).digest()[:8]))
    samples = {r["plan"]["id"]: {"scores": [], "ranks": [], "first": 0, "top5": 0} for r in rows}
    for _ in range(draws if rows else 0):
        gamma = {c: rng.gammavariate(weights[c] * 60, 1) for c in CRITERIA}
        total = sum(gamma.values())
        trial = {c: gamma[c] / total for c in CRITERIA}
        order = sorted(rows, key=lambda r: (-aggregate(r["utilities"], trial)[0], r["plan"]["id"]))
        top_ids = {r["plan"]["id"] for r in diversify(order)}
        for i, row in enumerate(order):
            sample = samples[row["plan"]["id"]]
            sample["scores"].append(aggregate(row["utilities"], trial)[0])
            sample["ranks"].append(i + 1)
            sample["first"] += i == 0
            sample["top5"] += row["plan"]["id"] in top_ids
    for row in rows:
        s = samples[row["plan"]["id"]]
        scores = sorted(s["scores"])
        row["stability"] = {"pTop1": s["first"] / max(draws, 1), "pTop5": s["top5"] / max(draws, 1),
                            "meanRank": sum(s["ranks"]) / max(draws, 1),
                            "scoreInterval": [scores[int(draws * 0.025)], scores[min(draws - 1, int(draws * 0.975))]]
                            if scores else [row["score"], row["score"]]}
    tied = len(top) >= 2 and (top[0]["score"] - top[1]["score"] < 1 or top[0]["stability"]["pTop1"] < 0.65)
    flip = None
    if len(top) >= 2:
        for step in range(1, 31):
            for source in CRITERIA:
                for target in CRITERIA:
                    amount = step / 100
                    if source == target or weights[source] < amount:
                        continue
                    changed = {**weights, source: weights[source] - amount, target: weights[target] + amount}
                    if aggregate(top[1]["utilities"], changed)[0] > aggregate(top[0]["utilities"], changed)[0]:
                        flip = {"from": source, "to": target, "amount": amount}
                        break
                if flip:
                    break
            if flip:
                break
    for i, row in enumerate(top):
        row["rank"] = 1 if tied and i < 2 else i + 1
        row["explanation"] = (f"Fit {row['fit']:.1f}/100; balance {row['balance']:.1f}/100; "
                              f"overall {row['score']:.1f}/100. " +
                              ("Effectively tied with the other leading plan. " if tied and i < 2 else "") +
                              "Terms remain subject to insurer underwriting and broker review.")
    return {"engine_version": ENGINE_VERSION, "weights_version": "user-v1" if not learned else "approved-model",
            "weights": weights, "top": top, "all": rows, "excluded": excluded,
            "needs_human": human, "joint_first": tied, "flip": flip, "draws": draws}
