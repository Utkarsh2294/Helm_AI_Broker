from app.engine.ranking import user_weights


def eligible_proposal():
    return {
        "eligible_for_shadow": True,
        "weights": user_weights([]),
        "champion_metrics": {"cases": 10, "ndcg3": 0.8, "top3_agreement": 0.8},
        "challenger_metrics": {"cases": 10, "ndcg3": 0.84, "top3_agreement": 0.9},
    }
