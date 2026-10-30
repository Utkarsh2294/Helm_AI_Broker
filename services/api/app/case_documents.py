"""Local document parsing with case-scoped, consented access to untrusted content."""

import base64
import binascii
import hashlib
from typing import Literal
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import select
from app.auth import identity
from app.db.models import Snapshot
from app.db.store import save_snapshot, audit
from app.documents import extract_document
from app.demo_documents import database
from app.medical_access import require_medical_access
from app.schemas import Model, DomainError, State
from app import service

router = APIRouter(prefix="/api/v1/cases")


class DocumentInput(Model):
    category: Literal["renewal", "policy", "supporting"] = "supporting"
    mime: Literal["application/pdf", "text/plain"]
    content_base64: str = Field(min_length=1, max_length=1_400_000)


@router.get("/{case_id}/documents")
def list_documents(case_id: str, request: Request, db=Depends(database, scope="function")):
    identity(db, request)
    service.get_case(db, case_id)
    rows = db.scalars(
        select(Snapshot)
        .where(Snapshot.case_id == case_id, Snapshot.kind == "case_document")
        .order_by(Snapshot.version)
    )
    return [
        {
            "id": row.id,
            "created_at": row.created_at,
            "category": row.body["category"],
            "pages": row.body["pages"],
            "mime": row.body["mime"],
            "sha256": row.body["sha256"],
            "source": f"doc:{row.id}",
            "content_requires_medical_access": True,
        }
        for row in rows
    ]


@router.post("/{case_id}/documents")
def upload_document(
    case_id: str, body: DocumentInput, request: Request, db=Depends(database, scope="function")
):
    user, session = identity(db, request)
    service.require_broker(user)
    case = service.get_case(db, case_id)
    if case.state not in {State.FACTFIND_REVIEW, State.NEEDS_INFO}:
        raise DomainError("Documents must be reviewed before fact-find sign-off", 409)
    require_medical_access(db, case, user, session)
    try:
        raw = base64.b64decode(body.content_base64, validate=True)
    except (ValueError, binascii.Error):
        raise DomainError("Invalid document encoding", 422)
    if len(raw) > 1_000_000:
        raise DomainError("Document exceeds the 1 MB upload limit", 413)
    parsed = extract_document(raw, body.mime)
    digest = hashlib.sha256(raw).hexdigest()
    for existing in db.scalars(
        select(Snapshot).where(Snapshot.case_id == case_id, Snapshot.kind == "case_document")
    ):
        if existing.body["sha256"] == digest:
            return {"id": existing.id, "sha256": digest, "duplicate": True}
    row = save_snapshot(
        db,
        case_id,
        "case_document",
        {
            "category": body.category,
            "mime": body.mime,
            "content_base64": body.content_base64,
            "sha256": digest,
            "text": parsed["text"],
            "pages": parsed["pages"],
            "uploaded_by": user.id,
            "extraction_method": "local_text_layer",
            "clinical_inference_performed": False,
            "automatically_changed_dnr": False,
        },
    )
    audit(
        db,
        case_id,
        "document_received",
        f"broker:{user.id}",
        {"document_id": row.id, "sha256": digest, "pages": parsed["pages"]},
    )
    return {
        "id": row.id,
        "sha256": digest,
        "pages": parsed["pages"],
        "source": f"doc:{row.id}",
        "needs_broker_verification": True,
    }


@router.get("/{case_id}/documents/{document_id}")
def read_document(case_id: str, document_id: str, request: Request, db=Depends(database, scope="function")):
    user, session = identity(db, request)
    case = service.get_case(db, case_id)
    require_medical_access(db, case, user, session)
    row = db.scalar(
        select(Snapshot).where(
            Snapshot.id == document_id, Snapshot.case_id == case_id, Snapshot.kind == "case_document"
        )
    )
    if not row:
        raise DomainError("Document not found", 404)
    audit(db, case_id, "document_accessed", f"broker:{user.id}", {"document_id": row.id})
    return Response(
        base64.b64decode(row.body["content_base64"]),
        media_type=row.body["mime"],
        headers={
            "Content-Disposition": f'attachment; filename="helm-document-{row.id}{".pdf" if row.body["mime"] == "application/pdf" else ".txt"}"',
            "X-Content-SHA256": row.body["sha256"],
        },
    )
