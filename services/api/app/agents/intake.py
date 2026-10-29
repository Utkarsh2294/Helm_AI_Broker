"""A1: grounded fact-find and needs research; no inferred medical conclusions."""

from app.schemas import DNR, Fact, QuoteRequest
from app.compliance.medical_firewall import screen_vulnerability

KNOWLEDGE = {
    "family": "Confirm children's cover, outpatient needs and preferred local hospitals.",
    "couple": "Confirm that both applicants agree on excess and hospital preferences.",
    "individual": "Confirm the preferred hospitals, excess and outpatient limits.",
}


def research_request(request: QuoteRequest) -> DNR:
    facts = {
        field: Fact(value=value, source=f"quote_request:{request.id}#{field}")
        for field, value in {
            "cover_type": request.cover_type,
            "postcode_district": request.postcode_district,
            "budget_annual_pence": request.needs.budget_annual_pence,
            "priorities": request.needs.priorities,
        }.items()
    }
    missing = list(request.missing_fields)
    if not request.consent_to_share:
        missing.append("consent_to_share")
    if not request.needs.coverage:
        missing.append("desired_coverage")
    return DNR(
        request_id=request.id,
        needs=request.needs.model_copy(deep=True),
        facts=facts,
        medical_items=list(request.medical_items),
        vulnerability_flags=sorted(
            set(request.vulnerability_flags + screen_vulnerability(" ".join(request.medical_items)))
        ),
        missing=sorted(set(missing)),
        consent_to_share=request.consent_to_share,
        hypotheses=[f"Hypothesis (not confirmed): {KNOWLEDGE[request.cover_type]} [kb:pmi-household-v1]"],
    )
