"""Authenticated demo consumer actions and scoped broker policy-buying views."""

from typing import Literal
from fastapi import APIRouter, Depends, Request
from pydantic import Field
from app import service
from app.auth import identity
from app.demo_documents import database
from app.schemas import Model, DomainError
from app.buying_service import require_demo, published_choices, select_quote

router = APIRouter(prefix="/api/v1")


def broker(user):
    if user.role not in {"authorised_broker", "senior_broker", "lead_broker", "admin"}:
        raise DomainError("An authorised broker must perform this demo action", 403)


class QuoteSelection(Model):
    selected_plan_id: str = Field(min_length=1, max_length=200)
    pack_hash: str = Field(min_length=64, max_length=64)
    confirm_selection: Literal[True]


@router.get("/policy-buying/choices/{case_id}")
def choices(case_id: str, request: Request, db=Depends(database, scope="function")):
    user, _ = identity(db, request)
    require_demo()
    case = service.get_case(db, case_id)
    pack, plans = published_choices(db, case)
    return {
        "demo": True,
        "case_id": case.id,
        "pack_hash": pack.body["pack_hash"],
        "plans": [
            {
                key: plan.get(key)
                for key in ("id", "name", "insurerId", "annualPremiumPence", "underwritingType")
            }
            for plan in plans
        ],
    }


@router.post("/consumer/cases/{case_id}/select-quote")
def consumer_select(
    case_id: str, body: QuoteSelection, request: Request, db=Depends(database, scope="function")
):
    user, session = identity(db, request)
    broker(user)
    row = select_quote(db, case_id, body.selected_plan_id, body.pack_hash, session.id, user)
    return {"id": row.id, "case_id": row.case_id, "stage": row.stage, "demo": True}
