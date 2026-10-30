import json
from pathlib import Path
from app.compliance.medical_ambiguity import check_medical_ambiguity
from app.config import ROOT


def test_fifty_synthetic_wording_scenarios_route_at_least_48_correctly():
    fixtures = json.loads((Path(ROOT) / "tools/eval-sets/medical_ambiguity.json").read_text())
    assert len(fixtures) == 50
    correct = sum(
        ("HALT" if check_medical_ambiguity({"medical_items": [item["text"]]}) else "PROCEED")
        == item["expected"]
        for item in fixtures
    )
    assert correct >= 48, f"{correct}/50 synthetic wording routes matched"


def test_triage_never_turns_a_condition_into_an_exclusion_or_diagnosis():
    result = check_medical_ambiguity({"medical_items": ["Possibly asthma."]})
    assert result["code"] == "H5"
    assert set(result) == {"code", "phase_alias", "rule_ids", "message"}
    assert "asthma" not in json.dumps(result)
