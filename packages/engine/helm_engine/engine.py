"""Helm Broker Portal - recommendation engine (production Python port).

Faithful port of the verified JavaScript reference (engine.reference.js).
Pure standard library, deterministic, no I/O. The LLM never computes or changes
scores; it only narrates them.

Wire format: dict keys are camelCase (shared with the JS frontend and the JSON
contract). Money is integer pence. All utilities are ABSOLUTE (not
cohort-relative) so adding or removing a quote can never reorder the others.
"""
from __future__ import annotations

import math
from typing import Any, Callable

CRITERIA = [
    "affordability", "coverage", "network", "underwriting",
    "insurer_quality", "process_ease", "terms_clarity",
]

_MASK = 0xFFFFFFFF


def clamp(x: float, a: float = 0.0, b: float = 1.0) -> float:
    return min(b, max(a, x))


def _sum(xs) -> float:
    s = 0.0
    for x in xs:
        s += x
    return s


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def _exp(x: float) -> float:
    try:
        return math.exp(x)
    except OverflowError:
        return math.inf


def _js_round(x: float) -> int:
    """JavaScript Math.round (half rounds toward +infinity)."""
    return math.floor(x + 0.5)


def _sign(x: float) -> int:
    return (x > 0) - (x < 0)


def _get(d: Any, key: str, default: Any = None) -> Any:
    """JS `d?.[key] ?? default`."""
    if d is None:
        return default
    v = d.get(key) if isinstance(d, dict) else None
    return default if v is None else v


# ---------- 1. Weights ----------
def roc_weights(m: int) -> list[float]:
    """Rank-Order Centroid: w_i = (1/m) * sum_{k=i..m} 1/k (i is 1-indexed)."""
    return [
        _sum(1.0 / (i + 1 + k) for k in range(m - i)) / m
        for i in range(m)
    ]


def user_weights(priority_order: list[str], criteria: list[str] | None = None) -> dict[str, float]:
    """Most important first (may be partial). Unranked criteria share 15% equally."""
    criteria = criteria or CRITERIA
    ranked = [c for c in priority_order if c in criteria]
    rest = [c for c in criteria if c not in ranked]
    mass_ranked = 0.85 if rest else 1.0
    roc = roc_weights(len(ranked) or 1)
    w: dict[str, float] = {}
    for i, c in enumerate(ranked):
        w[c] = mass_ranked * roc[i]
    for c in rest:
        w[c] = 0.15 / len(rest)
    return w


def combine_weights(w_user, w_learned, lam: float = 0.25, cap: float = 0.3, floor: float = 0.02):
    """Blend user and learned weights. Per-criterion change is bounded to +/-cap
    (and a floor) AFTER normalisation, via bisection on a common shift."""
    lam = min(lam, 0.25)
    lo, hi, blended = {}, {}, {}
    for c in CRITERIA:
        base = w_user[c]
        learned = _get(w_learned, c, base)
        blended[c] = (1 - lam) * base + lam * learned
        lo[c] = max(floor, base * (1 - cap))
        hi[c] = max(lo[c], base * (1 + cap))

    def total(s: float) -> float:
        return _sum(clamp(blended[c] + s, lo[c], hi[c]) for c in CRITERIA)

    a, b = -1.0, 1.0
    for _ in range(80):
        m = (a + b) / 2
        if total(m) < 1:
            a = m
        else:
            b = m
    s = (a + b) / 2
    out = {c: clamp(blended[c] + s, lo[c], hi[c]) for c in CRITERIA}
    t = _sum(out.values())
    if abs(t - 1) > 1e-9:  # only if bounds were infeasible
        for c in CRITERIA:
            out[c] /= t
    return out


# ---------- 2. Hard gates (non-compensatory) ----------
def gate(plan: dict, ctx: dict) -> dict:
    reasons: list[str] = []
    needs_human = False
    status = plan.get("status")
    if status and status != "quoted":
        reasons.append(f"insurer_{status}")
    cap = ctx.get("hardBudgetCapPence")
    if cap and plan["annualPremiumPence"] > cap:
        reasons.append("over_hard_budget_cap")
    for k, spec in (ctx.get("desiredCoverage") or {}).items():
        if spec.get("mustHave") and _get(plan.get("coverage"), k, 0) < spec["level"]:
            reasons.append(f"must_have_missing:{k}")
    allowed = ctx.get("allowedUnderwriting")
    if allowed is not None and plan.get("underwritingType") not in allowed:
        reasons.append("underwriting_not_allowed")
    if plan.get("basePremiumPence") is not None:
        expected = _js_round(plan["basePremiumPence"] * (1 + _get(ctx, "iptRate", 0.12)))
        if abs(expected - plan["annualPremiumPence"]) > max(2, plan["annualPremiumPence"] / 10000):
            needs_human = True
            reasons.append("premium_arithmetic_mismatch")
    if plan.get("medicalFlagsAmbiguous"):
        needs_human = True
        reasons.append("ambiguous_medical_terms_route_to_human")
    hard = [r for r in reasons if r not in ("premium_arithmetic_mismatch", "ambiguous_medical_terms_route_to_human")]
    return {"pass": len(hard) == 0 and not needs_human, "needsHuman": needs_human, "reasons": reasons}


# ---------- 3. Criterion utilities in [0,1] ----------
def utilities(plan: dict, ctx: dict) -> dict:
    freq = _get(ctx, "claimFreq", 0.25)
    exp_claim = _get(ctx, "expectedClaimPence", 300000)
    teco = plan["annualPremiumPence"] + freq * min(_get(plan, "excessPence", 0), exp_claim)
    bench = ctx["bench"]
    budget = _get(ctx, "budgetAnnualPence", bench["p90"] * 0.9)
    u_budget = 1 / (1 + _exp(6 * (teco / budget - 1)))
    u_ref = clamp((bench["p90"] - teco) / (bench["p90"] - bench["p10"]))
    affordability = 0.5 * u_budget + 0.5 * u_ref

    dcov = ctx.get("desiredCoverage") or {}
    imp_sum = _sum(d["importance"] for d in dcov.values()) or 1
    coverage = _sum(
        d["importance"] * clamp(_get(plan.get("coverage"), k, 0) / max(d["level"], 1))
        for k, d in dcov.items()
    ) / imp_sum

    network = (
        0.6 * clamp(plan["hospitalListLevel"] / max(_get(ctx, "desiredHospitalLevel", 1), 1))
        + 0.4 * clamp(_get(plan, "preferredHospitalShare", 0))
    )

    burden = clamp(_sum(_get(plan, "exclusionSeverities", [])) / _get(ctx, "maxSeverity", 10))
    type_match = 1 if plan.get("underwritingType") == ctx.get("preferredUnderwriting") else 0.5
    underwriting = 0.7 * (1 - burden) + 0.3 * type_match

    st = plan.get("insurerStats") or {}
    n0, p0 = 30, _get(ctx, "priorUpheldRate", 0.25)
    n = _get(st, "n", 0)
    shrunk = (n * _get(st, "upheldRate", p0) + n0 * p0) / (n + n0)
    insurer_quality = (
        0.5 * (1 - shrunk)
        + 0.3 * clamp(_get(st, "finStrength", 0.5))
        + 0.2 * clamp(_get(st, "slaScore", 0.5))
    )

    process_ease = clamp(
        1
        - 0.6 * (_get(plan, "docsUnavailable", 0) / max(_get(plan, "docsRequired", 1), 1))
        - 0.4 * min(_get(plan, "turnaroundDays", 7) / 14, 1)
    )

    terms_clarity = clamp(
        0.5 * _get(plan, "ipidCompleteness", 0.5)
        + 0.3 * _get(plan, "plainLanguage", 0.5)
        + 0.2 * (1 - min(_get(plan, "exclusionsCount", 10) / 20, 1))
    )

    return {
        "affordability": affordability, "coverage": coverage, "network": network,
        "underwriting": underwriting, "insurer_quality": insurer_quality,
        "process_ease": process_ease, "terms_clarity": terms_clarity, "_teco": teco,
    }


# ---------- 4. Aggregation: additive fit + fixed-reference TOPSIS balance ----------
def aggregate(u: dict, w: dict) -> dict:
    wsm = _sum(w[c] * u[c] for c in CRITERIA)
    d_plus = math.sqrt(_sum(w[c] * (1 - u[c]) ** 2 for c in CRITERIA))
    d_minus = math.sqrt(_sum(w[c] * u[c] ** 2 for c in CRITERIA))
    topsis = d_minus / ((d_plus + d_minus) or 1)
    score = 100 * (0.7 * wsm + 0.3 * topsis)
    points = {c: round(100 * w[c] * u[c], 2) for c in CRITERIA}
    return {"score": score, "fit": 100 * wsm, "balance": 100 * topsis, "points": points}


def rank_plans(plans: list[dict], ctx: dict, weights: dict) -> dict:
    rows, excluded = [], []
    for p in plans:
        g = gate(p, ctx)
        if not g["pass"]:
            excluded.append({"id": p["id"], "reasons": g["reasons"], "needsHuman": g["needsHuman"]})
            continue
        u = utilities(p, ctx)
        rows.append({"id": p["id"], "insurerId": p.get("insurerId"), "u": u, **aggregate(u, weights)})
    rows.sort(key=lambda r: (-r["score"], r["id"]))
    return {"rows": rows, "excluded": excluded}


def diversify(rows: list[dict], k: int = 5, max_per_insurer: int = 2) -> list[dict]:
    out, count = [], {}
    for r in rows:
        if count.get(r["insurerId"], 0) >= max_per_insurer:
            continue
        out.append(r)
        count[r["insurerId"]] = count.get(r["insurerId"], 0) + 1
        if len(out) == k:
            break
    return out


# ---------- 5. Uncertainty: Monte-Carlo over weights (Dirichlet) ----------
def _imul(a: int, b: int) -> int:
    return (a * b) & _MASK


def mulberry32(seed: int) -> Callable[[], float]:
    a = seed & _MASK

    def rng() -> float:
        nonlocal a
        a = (a + 0x6D2B79F5) & _MASK
        t = _imul(a ^ (a >> 15), 1 | a)
        t = ((t + _imul(t ^ (t >> 7), 61 | t)) & _MASK) ^ t
        return ((t ^ (t >> 14)) & _MASK) / 4294967296

    return rng


def _randn(rng) -> float:
    u = 0.0
    while u == 0:
        u = rng()
    v = rng()
    return math.sqrt(-2 * math.log(u)) * math.cos(2 * math.pi * v)


def _gamma_sample(shape: float, rng) -> float:  # Marsaglia-Tsang
    if shape < 1:
        return _gamma_sample(shape + 1, rng) * math.pow(rng(), 1 / shape)
    d = shape - 1 / 3
    c = 1 / math.sqrt(9 * d)
    while True:
        while True:
            x = _randn(rng)
            v = 1 + c * x
            if v > 0:
                break
        v = v ** 3
        u = rng()
        if u < 1 - 0.0331 * x ** 4 or math.log(u) < 0.5 * x * x + d * (1 - v + math.log(v)):
            return d * v


def mc_stability(rows: list[dict], weights: dict, draws: int = 1000, kappa: float = 60, seed: int = 7) -> dict:
    rng = mulberry32(seed)
    stat = {r["id"]: {"top1": 0, "top5": 0, "rankSum": 0, "scores": []} for r in rows}
    for _ in range(draws):
        g = [_gamma_sample(kappa * weights[c], rng) for c in CRITERIA]
        s = _sum(g)
        w = {c: g[i] / s for i, c in enumerate(CRITERIA)}
        sc = sorted(
            ({"id": r["id"], "s": aggregate(r["u"], w)["score"]} for r in rows),
            key=lambda x: -x["s"],
        )
        for i, x in enumerate(sc):
            st = stat[x["id"]]
            if i == 0:
                st["top1"] += 1
            if i < 5:
                st["top5"] += 1
            st["rankSum"] += i + 1
            st["scores"].append(x["s"])
    out = {}
    for r in rows:
        st = stat[r["id"]]
        st["scores"].sort()
        out[r["id"]] = {
            "pTop1": st["top1"] / draws, "pTop5": st["top5"] / draws,
            "meanRank": st["rankSum"] / draws,
            "ci95": [st["scores"][math.floor(0.025 * draws)], st["scores"][math.floor(0.975 * draws)]],
        }
    return out


# ---------- 6. Counterfactual: smallest weight shift that flips a vs b ----------
def flip_analysis(a: dict, b: dict, weights: dict, step: float = 0.01, max_shift: float = 0.3) -> dict:
    base = aggregate(a["u"], weights)["score"] - aggregate(b["u"], weights)["score"]
    best = None
    for frm in CRITERIA:
        for to in CRITERIA:
            if frm == to:
                continue
            d = step
            while d <= min(max_shift, weights[frm] - 0.02) + 1e-9:
                w = {**weights, frm: weights[frm] - d, to: weights[to] + d}
                diff = aggregate(a["u"], w)["score"] - aggregate(b["u"], w)["score"]
                if _sign(diff) != _sign(base):
                    if best is None or d < best["shift"]:
                        best = {"from": frm, "to": to, "shift": round(d, 2)}
                    break
                d += step
    return {"margin": round(base, 2), "flip": best}


# ---------- 7. Learning (Agent 5): Bradley-Terry on broker choices, MAP prior ----------
def learn_weights(base_w: dict, comparisons: list[dict], beta: float = 8, lr: float = 0.5,
                  epochs: int = 300, reg: float = 1.0) -> dict:
    theta0 = [math.log(base_w[c]) for c in CRITERIA]
    theta = list(theta0)

    def softmax(t):
        m = max(t)
        e = [math.exp(x - m) for x in t]
        s = _sum(e)
        return [x / s for x in e]

    for _ in range(epochs):
        w = softmax(theta)
        grad = [0.0] * len(CRITERIA)
        for cmp in comparisons:
            ub = [cmp["better"][c] for c in CRITERIA]
            uw = [cmp["worse"][c] for c in CRITERIA]
            sb = _sum(w[i] * ub[i] for i in range(len(w)))
            sw = _sum(w[i] * uw[i] for i in range(len(w)))
            p = _sigmoid(beta * (sb - sw))
            k = _get(cmp, "weight", 1) * beta * (1 - p)
            for i in range(len(grad)):
                grad[i] += k * (w[i] * (ub[i] - sb) - w[i] * (uw[i] - sw))
        n = max(len(comparisons), 1)
        for i in range(len(theta)):
            theta[i] += lr * (grad[i] / n - reg * 0.1 * (theta[i] - theta0[i]))
    w = softmax(theta)
    return {c: w[i] for i, c in enumerate(CRITERIA)}


def shrink_learned(base_w: dict, learned_w: dict, n: int, n0: int = 50) -> dict:
    a = n / (n + n0)
    return {c: (1 - a) * base_w[c] + a * learned_w[c] for c in CRITERIA}


def ndcg_at_k(ranked_ids: list[str], chosen_ids: list[str], k: int = 3) -> float:
    dcg = sum((1 if rid in chosen_ids else 0) / math.log2(i + 2) for i, rid in enumerate(ranked_ids[:k]))
    ideal = sum(1 / math.log2(i + 2) for i in range(min(k, len(chosen_ids))))
    return dcg / ideal if ideal else 0.0
