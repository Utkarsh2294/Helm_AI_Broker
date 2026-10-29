"""A5: bounded Bradley–Terry proposals with case-level holdout; never activates weights."""

import math
from app.engine.ranking import aggregate, combine_weights
from app.schemas import CRITERIA
from app.learning_fit import fit_bradley_terry


def preference_pairs(records: list[dict]) -> tuple[list[dict], list[str]]:
    pairs, disputed = [], []
    seen = set()
    for record in records:
        if record["id"] in seen:
            continue
        seen.add(record["id"])
        if "down" in record["survey"]["thumbs"].values():
            disputed.append(record["id"])
            continue
        rows = {r["plan"]["id"]: r for r in record["ranking"]["top"]}
        selected = record["selected"]
        for i, preferred in enumerate(selected):
            for other in rows:
                if other == preferred or other in selected[:i]:
                    continue
                pairs.append(
                    {
                        "case_id": record["case_id"],
                        "preferred": rows[preferred]["utilities"],
                        "other": rows[other]["utilities"],
                        "weight": 0.5 if other in selected else 1.0,
                    }
                )
    return pairs, disputed


def metrics(records: list[dict], weights: dict) -> dict:
    agreements, ndcgs = [], []
    for record in records:
        ordered = sorted(
            record["ranking"]["top"],
            key=lambda row: (-aggregate(row["utilities"], weights)[0], row["plan"]["id"]),
        )
        predicted = [r["plan"]["id"] for r in ordered[:3]]
        selected = record["selected"]
        agreements.append(len(set(predicted) & set(selected)) / 3)
        relevance = {p: 3 - i for i, p in enumerate(selected)}
        dcg = sum((2 ** relevance.get(p, 0) - 1) / math.log2(i + 2) for i, p in enumerate(predicted))
        ideal = sum((2 ** (3 - i) - 1) / math.log2(i + 2) for i in range(3))
        ndcgs.append(dcg / ideal)
    return {
        "top3_agreement": sum(agreements) / len(agreements) if agreements else 0,
        "ndcg3": sum(ndcgs) / len(ndcgs) if ndcgs else 0,
        "cases": len(records),
    }


def propose_improvement(records: list[dict], champion: dict | None = None, min_comparisons=30) -> dict:
    champion = champion or dict.fromkeys(CRITERIA, 1 / len(CRITERIA))
    pairs, disputed = preference_pairs(records)
    case_ids = sorted({p["case_id"] for p in pairs})
    base = {
        "comparison_count": len(pairs),
        "disputed": disputed,
        "activation": "requires_compliance_and_lead_broker_then_shadow",
        "auto_applied": False,
    }
    if len(pairs) < min_comparisons or len(case_ids) < 3:
        return {**base, "status": "insufficient_evidence", "weights": champion}
    holdout = set(case_ids[::5])
    training = [p for p in pairs if p["case_id"] not in holdout]
    fit = fit_bradley_terry(training, champion)
    proposed = combine_weights(champion, fit["weights"])
    evaluation = [r for r in records if r["case_id"] in holdout and r["id"] not in disputed]
    old, new = metrics(evaluation, champion), metrics(evaluation, proposed)
    improved = new["ndcg3"] > old["ndcg3"] + 1e-12 and new["top3_agreement"] >= old["top3_agreement"]
    return {
        **base,
        "status": "proposed" if improved else "no_improvement",
        "weights": proposed,
        "fit": {"iterations": fit["iterations"], "evidence_factor": fit["evidence_factor"]},
        "training_comparisons": len(training),
        "holdout_case_ids": sorted(holdout),
        "champion_metrics": old,
        "challenger_metrics": new,
        "eligible_for_shadow": improved,
        "report": "Weights are a proposal only. Review disputed examples before any model change. "
        "Synthetic demo feedback does not establish real-world ranking quality.",
    }
