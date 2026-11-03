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


def load_buying(db, case_id):
    case = service.get_case(db, case_id)
    buying = db.scalar(select(BuyingCase).where(BuyingCase.case_id == case.id).with_for_update())
    if not buying:
        raise DomainError("Policy-buying case not found", 404)
    return case, buying


def require_version(buying, expected_version):
    if buying.version != expected_version:
        raise DomainError("This buying case changed. Reload before recording your decision")
    if buying.closed_at:
        raise DomainError("This demo policy has already been issued")


def acknowledge_baseline(db, buying, actor):
    if buying.body.get("baseline_acknowledged"):
        return
    buying.body = {**buying.body, "baseline_acknowledged": stamp()}
    record_update(
        db,
        buying,
        "baseline_acknowledged",
        "Broker acknowledged the original underwriting basis and demo limitations",
        actor,
    )


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
    if case.assigned_to is None:
        case.assigned_to = user.id
    db.flush()
    record_update(
        db,
        buying,
        "quote_selected",
        "Demo consumer explicitly selected one published quote",
        f"demo-consumer:{user.id}",
    )
    prepare_initial(db, buying)
    return buying


def prepare_initial(db, buying):
    from app.buying_documents import add_document, current_documents
    from app.buying_templates import ipid, illustrative_start
    from app.policy_buying import next_buying_stage

    if "ipid" in current_documents(db, buying.id):
        return
    buying.body = {**buying.body, "illustrative_start": illustrative_start()}
    document = add_document(db, buying, "ipid", ipid(buying))
    buying.body = {**buying.body, "documents": {"ipid": {"id": document.id, "status": "draft"}}}
    buying.stage = next_buying_stage(buying.stage, "ipid_generated")
    record_update(db, buying, "ipid_generated", "Local demo agent prepared the IPID for broker review")
