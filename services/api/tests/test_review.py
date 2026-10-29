import pytest
from app.agents.ranking import rank_quotes
from app.agents.quotation import build_rfq, simulate_responses
from app.agents.review import assemble_pack, canonical_hash
from app.schemas import DomainError, Survey
from test_quotation import fixture_dnr


def test_pack_guards_and_content_binding():
    dnr = fixture_dnr()
    plans, _ = simulate_responses(build_rfq(dnr, signed_off=True))
    ranking = rank_quotes(dnr, plans, "r1")
    ids = [r["plan"]["id"] for r in ranking["top"][:3]]
    survey = Survey(thumbs=dict.fromkeys(ids, "up"))
    with pytest.raises(DomainError):
        assemble_pack(dnr, ranking, ids[:2], survey, ids)
    pack = assemble_pack(dnr, ranking, ids, survey, ids)
    body = {k: v for k, v in pack.items() if k != "pack_hash"}
    assert canonical_hash(body) == pack["pack_hash"]
    edited = assemble_pack(dnr, ranking, ids, survey, ids, "Broker's edited explanation")
    assert edited["pack_hash"] != pack["pack_hash"]
    assert "approved_by" not in pack
