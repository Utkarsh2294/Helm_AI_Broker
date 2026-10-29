import pytest
from app.agents.intake import research_request
from app.schemas import QuoteRequest, Needs, CoverageNeed
from app.compliance.medical_firewall import llm_profile, screen_vulnerability


@pytest.mark.parametrize("i", range(60))
def test_structured_field_extraction_and_hypothesis_labels(i):
    request = QuoteRequest(
        id=f"messy-{i}",
        name=f"Synthetic Applicant {i}",
        postcode_district=["M20", "BS8", "SW11"][i % 3],
        cover_type=["family", "individual", "couple"][i % 3],
        needs=Needs(
            budget_annual_pence=100000 + i * 1000, coverage={"cancer": CoverageNeed(level=3, must_have=True)}
        ),
        medical_items=[f"Medical canary {i}: exact consumer wording."],
    )
    dnr = research_request(request)
    assert dnr.facts["postcode_district"].value == request.postcode_district
    assert dnr.facts["budget_annual_pence"].value == request.needs.budget_annual_pence
    assert dnr.medical_items == request.medical_items
    assert all(h.startswith("Hypothesis") for h in dnr.hypotheses)
    assert request.medical_items[0] not in str(llm_profile(request))


@pytest.mark.parametrize(
    "text,expected",
    [
        ("recent divorce", "life_events"),
        ("I have dyslexia", "capability"),
        ("struggling financially", "resilience"),
        ("I am a carer", "health"),
    ],
)
def test_vulnerability_routing(text, expected):
    assert expected in screen_vulnerability(text)
