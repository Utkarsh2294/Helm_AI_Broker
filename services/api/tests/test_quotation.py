import pytest
from app.agents.intake import research_request
from app.agents.quotation import build_rfq, normalise_responses, premium_with_tax, simulate_responses
from app.schemas import DomainError, QuoteRequest, Needs, CoverageNeed


def fixture_dnr():
    return research_request(QuoteRequest(id="q1", name="Demo", needs=Needs(
        coverage={"cancer": CoverageNeed(level=3, must_have=True)})))


def test_release_guards_and_minimisation():
    dnr = fixture_dnr()
    with pytest.raises(DomainError):
        build_rfq(dnr, signed_off=False)
    dnr.medical_items = ["Consumer's exact wording"]
    with pytest.raises(DomainError):
        build_rfq(dnr, signed_off=True)
    rfq = build_rfq(dnr, signed_off=True, medical_released=True)
    assert "name" not in rfq.body
    assert len(rfq.partners) == 5
    assert rfq.body["medical_items"] == [{"category": "unspecified", "needs_clinical_underwriting": True}]
    assert dnr.medical_items[0] not in str(rfq.body)


def test_all_partners_and_adverse_scenarios():
    rfq = build_rfq(fixture_dnr(), signed_off=True)
    plans, board = simulate_responses(rfq)
    assert len(plans) == 30 and len(board) == 5
    assert all(p.annualPremiumPence == premium_with_tax(p.basePremiumPence) for p in plans)
    for scenario, state in [("decline", "declined"), ("late", "late"), ("medical", "clarification"),
                            ("referral", "referred")]:
        quotes, statuses = simulate_responses(rfq, scenario)
        assert len(quotes) == 24 and statuses[-1]["state"] == state


def test_duplicate_and_out_of_order_quotes_are_not_double_counted():
    rfq = build_rfq(fixture_dnr(), signed_off=True)
    quotes, _ = simulate_responses(rfq, "duplicate")
    assert len(quotes) == 32
    canonical = normalise_responses(quotes)
    assert len(canonical) == 30
    assert next(p for p in canonical if p.id == quotes[0].id).revision == 2
    bad = quotes[0].model_copy(update={"annualPremiumPence": 1})
    with pytest.raises(DomainError, match="Contradictory"):
        normalise_responses([quotes[0], bad])
