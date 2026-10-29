import pytest
from app.agents.intake import research_request
from app.agents.quotation import build_rfq, premium_with_tax, simulate_responses
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
    assert rfq.body["medical_items"] == dnr.medical_items


def test_all_partners_and_adverse_scenarios():
    rfq = build_rfq(fixture_dnr(), signed_off=True)
    plans, board = simulate_responses(rfq)
    assert len(plans) == 10 and len(board) == 5
    assert all(p.annualPremiumPence == premium_with_tax(p.basePremiumPence) for p in plans)
    for scenario, state in [("decline", "declined"), ("late", "late"), ("medical", "clarification"),
                            ("referral", "referred")]:
        quotes, statuses = simulate_responses(rfq, scenario)
        assert len(quotes) == 8 and statuses[-1]["state"] == state
