from app.agents.learning import metrics
from app.engine.ranking import user_weights
from app.schemas import CRITERIA


def test_heldout_metrics_preserve_the_consumers_original_priorities():
    budget = {**dict.fromkeys(CRITERIA, 0.5), "affordability": 0.9, "coverage": 0.1}
    cover = {**dict.fromkeys(CRITERIA, 0.5), "affordability": 0.1, "coverage": 0.9}
    record = {"selected": ["b", "a", "c"], "ranking": {"base_weights": user_weights(["coverage", "affordability", "network"]),
              "top": [{"plan": {"id": "a"}, "utilities": budget}, {"plan": {"id": "b"}, "utilities": cover},
                      {"plan": {"id": "c"}, "utilities": dict.fromkeys(CRITERIA, 0)}]}}
    assert metrics([record], None)["ndcg3"] == 1
