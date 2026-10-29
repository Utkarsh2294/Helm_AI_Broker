import copy
import pytest
from app.agents.intake import research_request
from app.agents.quotation import build_rfq, simulate_responses
from app.agents.ranking import rank_quotes
from app.agents.review import assemble_pack
from app.compliance.pack_validator import validate_pack
from app.schemas import QuoteRequest, Needs, CoverageNeed, Survey, DomainError


@pytest.fixture(scope="module")
def valid_pack():
    dnr = research_request(
        QuoteRequest(id="controls", name="Fictional", needs=Needs(coverage={"cancer": CoverageNeed(level=3)}))
    )
    plans, _ = simulate_responses(build_rfq(dnr, signed_off=True), "happy")
    ranking = rank_quotes(dnr, plans, "controls-ranking")
    selected = [r["plan"]["id"] for r in ranking["top"][:3]]
    return assemble_pack(dnr, ranking, selected, Survey(thumbs=dict.fromkeys(selected, "up")), selected)


@pytest.mark.parametrize(
    "control,field", [("C5", "ipid_reference"), ("C7", "premium_breakdown"), ("C9", "toba_reference")]
)
def test_plan_controls_reject_missing_evidence(valid_pack, control, field):
    pack = copy.deepcopy(valid_pack)
    del pack["manifest"]["plans"][0][field]
    with pytest.raises(DomainError, match=control):
        validate_pack(pack)


@pytest.mark.parametrize(
    "control,field",
    [("C6", "cancellation_notice"), ("C8", "remuneration_panel"), ("C10", "search_basis_statement")],
)
def test_pack_controls_reject_missing_evidence(valid_pack, control, field):
    pack = copy.deepcopy(valid_pack)
    del pack["manifest"][field]
    with pytest.raises(DomainError, match=control):
        validate_pack(pack)


def test_c3_personalised_explanations_reference_each_plan_and_priorities(valid_pack):
    for explanation, row in zip(valid_pack["plan_explanations"], valid_pack["plans"]):
        assert row["plan"]["name"] in explanation["text"]
        assert "affordability" in explanation["text"]


def test_c7_cannot_disguise_bad_tax_as_an_internally_consistent_sum(valid_pack):
    pack = copy.deepcopy(valid_pack)
    premium = pack["manifest"]["plans"][0]["premium_breakdown"]
    premium["annual_pence"] += 500
    premium["ipt_pence"] += 500
    with pytest.raises(DomainError, match="C7:tax_arithmetic"):
        validate_pack(pack)
