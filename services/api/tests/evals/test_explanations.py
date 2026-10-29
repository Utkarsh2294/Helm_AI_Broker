import pytest
from app.agents.guards import grounded, consumer_draft
from app.agents.ranking import rank_quotes
from app.agents.quotation import build_rfq, simulate_responses
from app.copilot import answer_question
from test_quotation import fixture_dnr


@pytest.mark.parametrize("i", range(30))
def test_grounded_dual_audience_explanations(i):
    dnr = fixture_dnr()
    plans, _ = simulate_responses(build_rfq(dnr, signed_off=True))
    ranking = rank_quotes(dnr, plans, f"explanation-{i}")
    assert all(row["explanation_grounded"] and row["consumer_draft_grounded"] for row in ranking["top"])
    assert not grounded("The premium is 123456789", ranking)
    answer = answer_question(ranking, "Why is #2 above #3?")
    assert len(answer["cited_fields"]) == 2
    assert "point differences" in answer["answer"]
