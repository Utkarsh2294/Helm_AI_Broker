"""A2: minimised RFQs, eligible-partner fan-out and deterministic demo replies."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from app.schemas import DNR, DomainError, Model, Plan

Scenario = Literal["happy", "decline", "late", "arithmetic", "medical", "duplicate", "referral", "injection"]
PARTNERS = [
    {"id": key, "name": name, "fca_status": "authorised", "toba_status": "active", "fictional": True}
    for key, name in [("northgate", "Northgate Health"), ("cedar", "Cedar Mutual"),
                      ("vale", "Vale Assurance"), ("haven", "Haven Medical"), ("alder", "Alder Health")]
]


def premium_with_tax(base: int, rate: Decimal = Decimal("0.12")) -> int:
    return base + int((Decimal(base) * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class RFQ(Model):
    request_id: str
    dnr_version: int
    deadline: datetime
    partners: list[str]
    body: dict
    demo: bool = True


def build_rfq(dnr: DNR, *, signed_off: bool, medical_released: bool = False,
              now: datetime | None = None) -> RFQ:
    if not signed_off or dnr.missing or not dnr.consent_to_share:
        raise DomainError("Complete and sign off the fact-find before releasing quotations")
    if dnr.medical_items and not medical_released:
        raise DomainError("Medical text requires explicit broker release", 403)
    body = {
        "needs": dnr.needs.model_dump(),
        "postcode_district": dnr.facts["postcode_district"].value,
        "cover_type": dnr.facts["cover_type"].value,
    }
    if dnr.medical_items:
        body["medical_items"] = list(dnr.medical_items)
    return RFQ(request_id=dnr.request_id, dnr_version=dnr.version,
               deadline=(now or datetime.now(timezone.utc)) + timedelta(hours=6),
               partners=[p["id"] for p in PARTNERS
                         if p["toba_status"] == "active" and p["fca_status"] == "authorised"], body=body)


def simulate_responses(rfq: RFQ, scenario: Scenario = "happy",
                       tax_rate: Decimal = Decimal("0.12")) -> tuple[list[Plan], list[dict]]:
    """Fictional catalogue only; live network delivery is intentionally separate."""
    plans, board = [], []
    for i, partner in enumerate(PARTNERS):
        if partner["id"] not in rfq.partners:
            continue
        state = "quoted"
        if i == 4:
            state = {"decline": "declined", "late": "late", "referral": "referred",
                     "medical": "clarification"}.get(scenario, "quoted")
        board.append({**partner, "state": state, "response_count": 0 if state != "quoted" else 2,
                      "injection_blocked": scenario == "injection" and i == 4})
        if state != "quoted":
            continue
        for j in range(2):
            base = 78000 + i * 13500 + j * 16000
            plan_id = f"{partner['id']}-{'plus' if j else 'essential'}"
            plans.append(Plan(
                id=plan_id, insurerId=partner["id"], name=f"{partner['name']} {'Plus' if j else 'Essential'}",
                basePremiumPence=base,
                annualPremiumPence=premium_with_tax(base, tax_rate) + (1000 if scenario == "arithmetic" and i == 0 else 0),
                coverage={"cancer": 3, "mental": 2 + j, "outpatient": 2 + j},
                excessPence=25000 if j == 0 else 10000, hospitalListLevel=2 + j,
                preferredHospitalShare=0.65 + j * 0.25, docsRequired=5 if i == 3 else 3,
                docsUnavailable=3 if i == 3 else 0, turnaroundDays=2 + i,
                commissionPct=10 + i * 3, ipidUrl=f"https://example.test/ipid/{plan_id}",
                provenance={"basePremiumPence": f"demo:{rfq.request_id}:{plan_id}#premium",
                            "coverage": f"demo:{rfq.request_id}:{plan_id}#benefits"},
            ))
    return plans, board
