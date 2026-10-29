import pytest
from app.learning_fit import fit_bradley_terry
from app.engine.ranking import user_weights
from app.schemas import CRITERIA


def test_line_search_convergence_and_shrinkage():
    base = user_weights([])
    pairs = [{"preferred": {c: 1 if c == "coverage" else 0 for c in CRITERIA},
              "other": dict.fromkeys(CRITERIA, 0), "weight": 1} for _ in range(100)]
    first = fit_bradley_terry(pairs, base)
    second = fit_bradley_terry(pairs, base)
    assert first == second
    assert first["iterations"] <= 200
    assert first["weights"]["coverage"] > base["coverage"]
    assert fit_bradley_terry(pairs[:10], base)["evidence_factor"] == pytest.approx(1 / 6)
    assert fit_bradley_terry(pairs[:50], base)["evidence_factor"] == 0.5
