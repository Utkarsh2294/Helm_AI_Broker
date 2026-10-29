import pytest
from pydantic import ValidationError
from app.schemas import Needs, Plan


def test_boundary_rejects_invalid_inputs():
    with pytest.raises(ValidationError):
        Needs(priorities=["commission"])
    with pytest.raises(ValidationError):
        Plan(id="x", insurerId="a", name="Bad", basePremiumPence=-1,
             annualPremiumPence=20, coverage={})
    with pytest.raises(ValidationError):
        Needs(priorities=["coverage", "coverage"])
