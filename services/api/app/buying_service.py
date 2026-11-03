"""Transactional policy buying; demo actions never create real cover."""

import hashlib
from sqlalchemy import select
from app import service
from app.config import settings
from app.db.models import Publication, stamp
from app.db.policy_buying import BuyingCase
from app.db.store import latest
from app.schemas import DomainError
from app.buying_updates import record_update


def require_demo():
    if settings().mode != "demo" or settings().partner_mode == "core":
        raise DomainError("Policy buying is available only with fictional demo partners", 403)


def published_choices(db, case):
    pack = latest(db, case.id, "pack")
    publication = db.scalar(select(Publication).where(Publication.case_id == case.id))
    if (
        case.state != "PUBLISHED"
        or not pack
        or not publication
        or publication.pack_hash != pack.body.get("pack_hash")
    ):
        raise DomainError("A published, signed recommendation is required")
    allowed = set(pack.body["selected"])
    return pack, [row["plan"] for row in pack.body["plans"] if row["plan"]["id"] in allowed]


def select_quote(db, case_id, plan_id, pack_hash, session_id, user):
    require_demo()
    case = service.get_case(db, case_id)
    existing = db.scalar(select(BuyingCase).where(BuyingCase.case_id == case.id).with_for_update())
    if existing:
        if existing.selected_plan_id == plan_id and existing.body["pack_hash"] == pack_hash:
            return existing
        raise DomainError("This case already has a confirmed consumer quote selection")
    pack, choices = published_choices(db, case)
    if pack.body["pack_hash"] != pack_hash:
        raise DomainError("The recommendation version changed; review it again")
    plan = next((plan for plan in choices if plan["id"] == plan_id), None)
    if not plan or plan.get("status", "quoted") != "quoted":
        raise DomainError("Choose a quoted plan from the published shortlist", 422)
    dnr = latest(db, case.id, "dnr")
    basis = str(dnr.body.get("needs", {}).get("preferred_underwriting", "")).lower() if dnr else ""
    if basis not in {"moratorium", "fmu"}:
        raise DomainError("The original fact-find has no recognised underwriting preference")
    # A new insurer quote is needed if the published offer has a different basis.
    if str(plan.get("underwritingType", "")).lower() != basis:
        raise DomainError("This quote's underwriting basis differs from the fact-find preference")
    safe_plan = {
        key: plan[key]
        for key in (
            "id",
            "name",
            "insurerId",
            "annualPremiumPence",
            "excessPence",
            "coverage",
            "hospitalListLevel",
            "preferredHospitalShare",
            "underwritingType",
            "revision",
            "ipidVersion",
        )
        if key in plan
    }
    buying = BuyingCase(
        case_id=case.id,
        selected_plan_id=plan_id,
        underwriting_basis=basis,
        body={
            "plan": safe_plan,
            "pack_hash": pack_hash,
            "selected_at": stamp(),
            "session_fingerprint": hashlib.sha256(session_id.encode()).hexdigest(),
            "fictional": True,
            "documents": {},
            "payment_frequency": "annual",
        },
    )
    db.add(buying)
    db.flush()
    record_update(
        db,
        buying,
        "quote_selected",
        "Demo consumer explicitly selected one published quote",
        f"demo-consumer:{user.id}",
    )
    return buying
