"""Broker-originated underwriting referrals preserve the ranking and quote evidence."""

from typing import Literal
from fastapi import APIRouter, Depends, Request
from pydantic import Field
from app.auth import identity
from app.db.models import Approval, utcnow
from app.db.store import latest, save_snapshot
from app.schemas import Model, DomainError, State
from app.config import settings
from app.demo_documents import database
from app import service

router = APIRouter(prefix="/api/v1/cases")


class ReferralRequest(Model):
    ranking_id: str = Field(min_length=1, max_length=100)
    plan_ids: list[str] = Field(min_length=1, max_length=5)
    reason: str = Field(min_length=20, max_length=2000)
    urgency: Literal["normal", "urgent"] = "normal"


class ReferralResolution(Model):
    referral_hash: str = Field(min_length=64, max_length=64)
    underwriter_reference: str = Field(min_length=3, max_length=200)
    reason: str = Field(min_length=30, max_length=2000)
    fictional_confirmation: bool = False


@router.post("/{case_id}/referrals")
def refer(case_id: str, body: ReferralRequest, request: Request, db=Depends(database, scope="function")):
    from app.plan_ratings import current_ratings

    user, _ = identity(db, request)
    service.require_broker(user)
    case = service.get_case(db, case_id)
    if case.state != State.BROKER_REVIEW:
        raise DomainError("Only a current comparison can be referred", 409)
    ranking = latest(db, case_id, "ranking")
    if not ranking or ranking.body["id"] != body.ranking_id:
        raise DomainError("Review the current ranking", 409)
    reviews = current_ratings(db, case_id, body.ranking_id, user.id)
    allowed = {row["plan"]["id"] for row in ranking.body["top"]}
    if len(set(body.plan_ids)) != len(body.plan_ids) or any(
        pid not in allowed or pid not in reviews or reviews[pid].decision != "REFER" for pid in body.plan_ids
    ):
        raise DomainError("Every referred plan needs your saved Refer to UW assessment", 422)
    if len(body.reason.strip()) < 20:
        raise DomainError("Explain the referral in at least 20 characters", 422)
    referral = save_snapshot(
        db,
        case_id,
        "broker_referral",
        {
            **body.model_dump(),
            "reason": body.reason.strip(),
            "by": user.id,
            "at": utcnow().isoformat(),
            "ranking_snapshot_id": ranking.id,
            "external_message_sent": False,
        },
    )
    service.transition(
        db,
        case,
        [case.state],
        State.UW_REFERRAL,
        "broker_referral_requested",
        f"broker:{user.id}",
        {"referral_hash": referral.body_hash, "plan_ids": body.plan_ids, "urgency": body.urgency},
    )
    return {"state": case.state, "referral_hash": referral.body_hash, "external_message_sent": False}


@router.post("/{case_id}/referrals/resolve")
def resolve(case_id: str, body: ReferralResolution, request: Request, db=Depends(database, scope="function")):
    user, _ = identity(db, request)
    service.require_broker(user)
    case = service.get_case(db, case_id)
    referral = latest(db, case_id, "broker_referral")
    if case.state != State.UW_REFERRAL or not referral:
        raise DomainError("No broker-originated referral is pending", 409)
    if settings().clock_mode != "demo" or not body.fictional_confirmation:
        raise DomainError(
            "Real underwriting requires verified partner evidence; use fictional confirmation only for a demo",
            403,
        )
    if body.referral_hash != referral.body_hash:
        raise DomainError("Referral changed. Review the current evidence.", 409)
    if len(body.reason.strip()) < 30 or len(body.underwriter_reference.strip()) < 3:
        raise DomainError("Record the underwriter reference and a reason of at least 30 characters", 422)
    save_snapshot(
        db,
        case_id,
        "referral_resolution",
        {**body.model_dump(), "by": user.id, "at": utcnow().isoformat(), "scope": "fictional_demo_only"},
    )
    db.add(Approval(case_id=case_id, gate="G3", user_id=user.id, payload_hash=referral.body_hash))
    service.transition(
        db,
        case,
        [case.state],
        State.BROKER_REVIEW,
        "broker_referral_resolved",
        f"broker:{user.id}",
        {"referral_hash": referral.body_hash, "fictional": True},
    )
    return {"state": case.state, "reassess_plans_required": True}
