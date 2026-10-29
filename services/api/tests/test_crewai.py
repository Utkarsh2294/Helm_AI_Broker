"""Framework spike: run all five steps without credentials or network access."""

import importlib.util
import pytest
from app.agents.runtime import run_agent
from app.agents.quotation import build_rfq
from app.schemas import DNR


@pytest.mark.skipif(
    importlib.util.find_spec("crewai") is None, reason="Install the agents extra for framework spike"
)
def test_five_agents_execute_through_crewai_flows():
    request = {
        "id": "framework-spike",
        "name": "Fictional Applicant",
        "needs": {"coverage": {"cancer": {"level": 3, "must_have": True}}},
    }
    dnr = run_agent("intake", request, "crewai")
    rfq = build_rfq(DNR.model_validate(dnr), signed_off=True)
    replies = run_agent("quotation", {"rfq": rfq.model_dump(mode="json"), "scenario": "happy"}, "crewai")
    ranking = run_agent(
        "ranking", {"dnr": dnr, "quotes": replies["quotes"], "id": "framework-ranking"}, "crewai"
    )
    ids = [r["plan"]["id"] for r in ranking["top"][:3]]
    pack = run_agent(
        "review",
        {
            "dnr": dnr,
            "ranking": ranking,
            "selected": ids,
            "survey": {"thumbs": dict.fromkeys(ids, "up")},
            "acknowledgements": ids,
        },
        "crewai",
    )
    learning = run_agent("learning", {"records": []}, "crewai")
    assert len(pack["plans"]) == 3 and len(pack["pack_hash"]) == 64
    assert learning["status"] == "insufficient_evidence"
