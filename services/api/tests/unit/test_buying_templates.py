from types import SimpleNamespace
from app.buying_templates import ipid, IPID_HEADINGS


def fixture(basis):
    return SimpleNamespace(
        underwriting_basis=basis,
        body={
            "illustrative_start": "2026-11-04",
            "plan": {
                "id": "demo",
                "insurerId": "fictional",
                "name": "Demo plan",
                "annualPremiumPence": 86200,
                "coverage": {"cancer": 3},
                "excessPence": 10000,
            },
        },
    )


def test_ipid_has_ten_sections_and_only_exclusion_changes_with_basis():
    mora, fmu = ipid(fixture("moratorium")), ipid(fixture("fmu"))
    assert [row["heading"] for row in mora["sections"]] == list(IPID_HEADINGS)
    assert [i for i, pair in enumerate(zip(mora["sections"], fmu["sections"])) if pair[0] != pair[1]] == [3]
    assert "862.00" in mora["sections"][7]["text"]
