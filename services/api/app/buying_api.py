"""Authenticated demo consumer actions and scoped broker policy-buying views."""

from typing import Literal
from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy import select, func
from pydantic import Field
from app import service
from app.auth import identity
from app.demo_documents import database
from app.schemas import Model, DomainError
from app.buying_service import require_demo, published_choices, select_quote
from app.buying_service import load_buying
from app.db.models import Case
from app.db.policy_buying import BuyingCase, BuyingUpdate, BuyingRead
from app.buying_documents import current_documents, document_versions
from app.buying_updates import mark_read
from app.case_access import visible_cases
from app.policy_buying import BuyingStage

router = APIRouter(prefix="/api/v1")


def summary(db, buying, case, user):
    seq = db.scalar(select(func.max(BuyingUpdate.seq)).where(BuyingUpdate.pb_case_id == buying.id)) or 0
    read = db.get(BuyingRead, (buying.id, user.id))
    return {
        "id": buying.id,
        "case_id": case.id,
        "client": case.profile.get("name", "Fictional client"),
        "plan": buying.body["plan"],
        "underwriting_basis": buying.underwriting_basis,
        "stage": buying.stage,
        "version": buying.version,
        "last_activity": buying.updated_at,
        "updates": max(0, seq - (read.seq if read else 0)),
        "latest_seq": seq,
        "pending_response": buying.pending_response,
        "policy_number": buying.policy_number,
        "closed_at": buying.closed_at,
        "demo": True,
    }


@router.get("/policy-buying")
def buying_list(
    request: Request,
    closed: bool = False,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db=Depends(database, scope="function"),
):
    user, _ = identity(db, request)
    query = (
        select(BuyingCase, Case)
        .join(Case, Case.id == BuyingCase.case_id)
        .where(
            visible_cases(user),
            BuyingCase.closed_at.is_not(None) if closed else BuyingCase.closed_at.is_(None),
        )
    )
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(
        query.order_by(BuyingCase.updated_at.desc(), BuyingCase.id).offset(offset).limit(limit)
    ).all()
    return {
        "items": [summary(db, buying, case, user) for buying, case in rows],
        "total": total,
        "next_offset": offset + len(rows) if offset + len(rows) < total else None,
    }


@router.get("/policy-buying/cases/{case_id}")
def buying_detail(case_id: str, request: Request, db=Depends(database, scope="function")):
    user, _ = identity(db, request)
    case, buying = load_buying(db, case_id)
    documents = current_documents(db, buying.id)
    statuses = buying.body.get("documents", {})
    return {
        **summary(db, buying, case, user),
        "stages": list(BuyingStage),
        "client_file": {
            key: case.profile.get(key) for key in ("name", "date_of_birth", "email", "phone", "postcode")
        },
        "baseline_acknowledged": bool(buying.body.get("baseline_acknowledged")),
        "documents": [
            {
                "id": row.id,
                "doc_type": kind,
                "version": row.version,
                "content": row.content,
                "status": statuses.get(kind, {}).get("status", "draft"),
                "edited_by_broker": row.edited_by_broker,
            }
            for kind, row in documents.items()
        ],
        "history": [
            {
                "id": row.id,
                "doc_type": row.doc_type,
                "version": row.version,
                "created_at": row.created_at,
                "edited_by_broker": row.edited_by_broker,
            }
            for row in document_versions(db, buying.id)
        ],
        "feed": [
            {"seq": row.seq, "type": row.update_type, "created_at": row.created_at, **row.body}
            for row in db.scalars(
                select(BuyingUpdate)
                .where(BuyingUpdate.pb_case_id == buying.id)
                .order_by(BuyingUpdate.seq.desc())
                .limit(100)
            )
        ],
    }


class ReadPosition(Model):
    seq: int = Field(ge=0)


@router.post("/policy-buying/cases/{case_id}/read")
def buying_read(case_id: str, body: ReadPosition, request: Request, db=Depends(database, scope="function")):
    user, _ = identity(db, request)
    _, buying = load_buying(db, case_id)
    return {"seq": mark_read(db, buying.id, user.id, body.seq)}


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
