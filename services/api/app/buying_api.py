"""Authenticated demo consumer actions and scoped broker policy-buying views."""

from typing import Literal
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import Response
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
from app.db.policy_buying import BuyingDocument
from app.buying_documents import current_documents, document_versions
from app.buying_updates import mark_read
from app.case_access import visible_cases
from app.policy_buying import BuyingStage
from app.buying_service import require_version, acknowledge_baseline

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
        "consumer_query": buying.body.get("consumer_query"),
        "banking_received": bool(buying.body.get("banking_received")),
        "package_hash": buying.body.get("package_hash"),
        "banking_verified": bool(buying.body.get("banking_verified")),
        "submission_reviewed": buying.body.get("submission_reviewed") == buying.body.get("package_hash")
        and bool(buying.body.get("package_hash")),
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


@router.get("/policy-buying/cases/{case_id}/documents/{document_id}.pdf")
def document_pdf(case_id: str, document_id: str, request: Request, db=Depends(database, scope="function")):
    from app.buying_pdf import build_pdf

    identity(db, request)
    _, buying = load_buying(db, case_id)
    document = db.get(BuyingDocument, document_id)
    if not document or document.pb_case_id != buying.id:
        raise DomainError("Buying document not found", 404)
    return Response(
        build_pdf(document.content, document.doc_type),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="demo-{document.doc_type}-v{document.version}.pdf"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/policy-buying/cases/{case_id}/read")
def buying_read(case_id: str, body: ReadPosition, request: Request, db=Depends(database, scope="function")):
    user, _ = identity(db, request)
    _, buying = load_buying(db, case_id)
    return {"seq": mark_read(db, buying.id, user.id, body.seq)}


def broker(user):
    if user.role not in {"authorised_broker", "senior_broker", "lead_broker", "admin"}:
        raise DomainError("An authorised broker must perform this demo action", 403)


class BuyingAction(Model):
    expected_version: int = Field(ge=1, strict=True)


class DocumentAction(BuyingAction):
    document_id: str = Field(min_length=1, max_length=36)


class Section(Model):
    heading: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=2000)


class DocumentEdit(DocumentAction):
    sections: list[Section] = Field(default_factory=list, max_length=20)
    instruction: str = Field(default="", max_length=2200)


def action_context(db, case_id, request, expected_version):
    user, session = identity(db, request)
    require_demo()
    broker(user)
    case, buying = load_buying(db, case_id)
    if case.state != "PUBLISHED":
        raise DomainError("Buying actions are unavailable while the source case is on hold or closed")
    require_version(buying, expected_version)
    return user, session, case, buying


@router.post("/policy-buying/cases/{case_id}/baseline")
def baseline(case_id: str, body: BuyingAction, request: Request, db=Depends(database, scope="function")):
    user, _, _, buying = action_context(db, case_id, request, body.expected_version)
    acknowledge_baseline(db, buying, f"broker:{user.id}")
    return {"acknowledged": True}


@router.post("/policy-buying/cases/{case_id}/documents/{kind}/edit")
def edit_document(
    case_id: str, kind: str, body: DocumentEdit, request: Request, db=Depends(database, scope="function")
):
    from app.buying_review import revise_document

    user, _, _, buying = action_context(db, case_id, request, body.expected_version)
    document = revise_document(
        db,
        buying,
        kind,
        body.document_id,
        [row.model_dump() for row in body.sections],
        body.instruction,
        f"broker:{user.id}",
    )
    return {"document_id": document.id, "version": document.version}


@router.post("/policy-buying/cases/{case_id}/documents/{kind}/send")
def approve_send(
    case_id: str, kind: str, body: DocumentAction, request: Request, db=Depends(database, scope="function")
):
    from app.buying_review import send_document

    user, _, _, buying = action_context(db, case_id, request, body.expected_version)
    if not user.can_approve:
        raise DomainError("Broker approval authority is required", 403)
    send_document(db, buying, kind, body.document_id, f"broker:{user.id}")
    return {"sent": True, "demo": True}


class QuoteSelection(Model):
    selected_plan_id: str = Field(min_length=1, max_length=200)
    pack_hash: str = Field(min_length=64, max_length=64)
    confirm_selection: Literal[True]


class ConsumerResponse(DocumentAction):
    decision: Literal["confirm", "change"]
    note: str = Field(default="", max_length=2000)


class DeclarationSignature(DocumentAction):
    confirm_signature: Literal[True]


class FinalSubmission(DocumentAction):
    package_hash: str = Field(min_length=64, max_length=64)
    confirm_send: Literal[True]


@router.post("/policy-buying/cases/{case_id}/submission/send")
def submission_send(
    case_id: str, body: FinalSubmission, request: Request, db=Depends(database, scope="function")
):
    from app.buying_submission import send_package

    user, _ = identity(db, request)
    broker(user)
    require_demo()
    case, buying = load_buying(db, case_id)
    if not buying.closed_at:
        if case.state != "PUBLISHED":
            raise DomainError("The source case must be published and free of holds")
        require_version(buying, body.expected_version)
    return send_package(db, case, buying, body.document_id, body.package_hash, user)


@router.post("/policy-buying/cases/{case_id}/submission/review")
def submission_review(
    case_id: str, body: DocumentAction, request: Request, db=Depends(database, scope="function")
):
    from app.buying_submission import review_package

    user, _, case, buying = action_context(db, case_id, request, body.expected_version)
    if not user.can_approve:
        raise DomainError("Broker approval authority is required", 403)
    review_package(db, case, buying, body.document_id, f"broker:{user.id}")
    return {"reviewed": True}


@router.post("/policy-buying/cases/{case_id}/banking/reveal")
def banking_reveal(
    case_id: str, body: BuyingAction, request: Request, db=Depends(database, scope="function")
):
    from app.auth.mfa import load_challenge
    from app.buying_banking import reveal_banking
    from fastapi.responses import JSONResponse

    user, session, _, buying = action_context(db, case_id, request, body.expected_version)
    proof = load_challenge(db, request.headers.get("X-Step-Up", ""), "step-up")
    if proof.user_id != user.id or proof.body.get("session_id") != session.id or not user.can_approve:
        raise DomainError("Fresh broker verification for this session is required", 403)
    proof.consumed = True
    return JSONResponse(
        reveal_banking(db, buying, f"broker:{user.id}"), headers={"Cache-Control": "no-store"}
    )


@router.post("/policy-buying/cases/{case_id}/banking/verify")
def banking_verify(
    case_id: str, body: BuyingAction, request: Request, db=Depends(database, scope="function")
):
    from app.buying_banking import verify_banking

    user, _, _, buying = action_context(db, case_id, request, body.expected_version)
    if not user.can_approve:
        raise DomainError("Broker approval authority is required", 403)
    verify_banking(db, buying, f"broker:{user.id}")
    return {"verified": True, "account_ending": "1234", "demo": True}


@router.post("/policy-buying/cases/{case_id}/banking/complete")
def banking_complete(
    case_id: str, body: DeclarationSignature, request: Request, db=Depends(database, scope="function")
):
    from app.buying_banking import complete_banking

    user, _, _, buying = action_context(db, case_id, request, body.expected_version)
    complete_banking(db, buying, body.document_id, f"demo-consumer:{user.id}")
    return {"received": True, "account_ending": "1234", "demo": True}


@router.post("/policy-buying/cases/{case_id}/declaration/approve")
def declaration_approve(
    case_id: str, body: DocumentAction, request: Request, db=Depends(database, scope="function")
):
    from app.buying_underwriting import approve_declaration

    user, session, case, buying = action_context(db, case_id, request, body.expected_version)
    approve_declaration(db, case, buying, body.document_id, user, session)
    return {"approved": True}


@router.get("/policy-buying/cases/{case_id}/medical-response")
def medical_response(case_id: str, request: Request, db=Depends(database, scope="function")):
    from app.medical_access import require_medical_access
    from app.db.platform import MedicalAccess
    from app.db.policy_buying import BuyingMedicalResponse
    from app.db.store import audit

    user, session = identity(db, request)
    case, buying = load_buying(db, case_id)
    require_medical_access(db, case, user, session)
    reference = buying.body.get("declaration_response") or {}
    current = current_documents(db, buying.id).get("fmu_questionnaire")
    row = db.scalar(
        select(BuyingMedicalResponse).where(BuyingMedicalResponse.document_id == reference.get("document_id"))
    )
    if not row or not current or current.id != row.document_id:
        raise DomainError("No current completed FMU response is recorded", 404)
    audit(db, case.id, "pb.medical_response_viewed", f"broker:{user.id}", {"document_id": current.id})
    from fastapi.responses import JSONResponse

    return JSONResponse(
        {
            "answers": row.body["answers"],
            "fictional": True,
            "expires_at": db.get(MedicalAccess, (session.id, case.id)).expires_at,
        },
        headers={"Cache-Control": "no-store"},
    )


@router.post("/policy-buying/cases/{case_id}/declaration/complete")
def declaration_complete(
    case_id: str, body: DeclarationSignature, request: Request, db=Depends(database, scope="function")
):
    from app.buying_underwriting import complete_declaration

    user, _, _, buying = action_context(db, case_id, request, body.expected_version)
    complete_declaration(db, buying, body.document_id, f"demo-consumer:{user.id}")
    return {"completed": True, "broker_approval_required": True}


@router.post("/policy-buying/cases/{case_id}/documents/{kind}/respond")
def simulate_response(
    case_id: str, kind: str, body: ConsumerResponse, request: Request, db=Depends(database, scope="function")
):
    from app.buying_review import consumer_response

    user, _, _, buying = action_context(db, case_id, request, body.expected_version)
    consumer_response(
        db, buying, kind, body.document_id, body.decision, body.note, f"demo-consumer:{user.id}"
    )
    return {"recorded": True, "demo": True}


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
