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


def test_ipid_export_has_two_pages_and_every_page_is_watermarked(tmp_path):
    import pymupdf
    from app.buying_pdf import build_pdf
    from app.buying_templates import WATERMARK

    raw = build_pdf(ipid(fixture("moratorium")), "ipid")
    with pymupdf.open(stream=raw, filetype="pdf") as document:
        assert len(document) == 2
        assert all(WATERMARK in page.get_text() for page in document)
        assert all(heading in "".join(page.get_text() for page in document) for heading in IPID_HEADINGS)


def test_toba_is_fictional_and_has_no_internal_commission_percentage():
    from app.buying_templates import toba
    import json

    text = json.dumps(toba())
    assert "eight weeks" in text and "six months" in text
    assert "DEMO-NOT-REGISTERED" in text
    assert "commissionPct" not in text and "%" not in text
