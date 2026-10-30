"""Executable fictional P11 review; no record here grants live launch permission."""

from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy import select
from app.auth import identity
from app.agents.review import canonical_hash
from app.db.models import Approval, Case, Publication, Activity, User, utcnow
from app.db.store import latest, save_snapshot, verify_chain, audit
from app.demo_documents import database, demo_only, manifest, DISCLAIMER
from app.demo_documents import document_pdf
from app.schemas import Model, DomainError, QuoteRequest, State
from app import service

router = APIRouter(prefix="/api/v1/demo/showcase")
REQUEST_ID = "demo-pilot-showcase-v1"
CHECKLIST = {
    "fictional_only": "I am reviewing fictional documents and accounts for a demonstration.",
    "documents_reviewed": "I reviewed the document pack, its limitations and current version.",
    "workflow_reviewed": "I reviewed the broker-approved case and its audit evidence.",
    "risks_recorded": "I understand the unresolved live security, privacy and acceptance gates.",
    "no_live_authority": "This decision does not authorise real customer processing or claim FCA approval.",
}


def showcase_case(db):
    return db.scalar(select(Case).where(Case.core_request_id == REQUEST_ID))


def review_hash(case, manifest_hash, pack_hash):
    return canonical_hash(
        {
            "case_id": case.id,
            "documents_hash": manifest_hash,
            "pack_hash": pack_hash,
            "scope": "fictional_demo_only",
        }
    )


def status(db):
    case = showcase_case(db)
    items = manifest()
    document_hash = canonical_hash(items)
    pack = latest(db, case.id, "pack") if case else None
    pack_hash = pack.body.get("pack_hash") if pack else None
    binding = review_hash(case, document_hash, pack_hash) if case else None
    approvals = (
        db.scalars(
            select(Approval).where(
                Approval.case_id == case.id, Approval.gate == "DEMO_P11", Approval.payload_hash == binding
            )
        ).all()
        if case
        else []
    )
    reviewers = [
        {
            "user_id": a.user_id,
            "name": db.get(User, a.user_id).name,
            "role": db.get(User, a.user_id).role,
            "at": a.created_at,
        }
        for a in approvals
    ]
    publication = (
        db.scalar(
            select(Publication).where(Publication.case_id == case.id, Publication.pack_hash == pack_hash)
        )
        if case and pack_hash
        else None
    )
    g2 = (
        db.scalar(
            select(Approval).where(
                Approval.case_id == case.id, Approval.gate == "G2", Approval.payload_hash == pack_hash
            )
        )
        if publication
        else None
    )
    events = (
        db.scalars(select(Activity).where(Activity.case_id == case.id).order_by(Activity.seq)).all()
        if case
        else []
    )
    ready = bool(
        g2
        and verify_chain(events)
        and {r["role"] for r in reviewers} == {"compliance_officer", "legal_reviewer"}
    )
    return {
        "fictional": True,
        "disclaimer": DISCLAIMER,
        "case_id": case.id if case else None,
        "case_state": case.state if case else None,
        "documents": items,
        "manifest_hash": document_hash,
        "review_hash": binding,
        "workflow_published": bool(g2),
        "chain_verified": bool(events and verify_chain(events)),
        "checklist": CHECKLIST,
        "reviews": reviewers,
        "demo_ready": ready,
        "live_release_approved": False,
    }


@router.get("")
def get_showcase(request: Request, db=Depends(database, scope="function")):
    demo_only()
    identity(db, request)
    return status(db)


@router.post("")
def create_showcase(request: Request, db=Depends(database, scope="function")):
    demo_only()
    user, _ = identity(db, request)
    service.require_broker(user)
    case = service.import_request(
        db,
        QuoteRequest(
            id=REQUEST_ID,
            name="Morgan Demo — fictional showcase",
            needs={
                "budget_annual_pence": 180000,
                "coverage": {
                    "cancer": {"level": 3, "must_have": True},
                    "mental": {"level": 2},
                    "outpatient": {"level": 3},
                },
            },
        ),
    )
    if not latest(db, case.id, "demo_documents"):
        from app.documents import extract_document
        import hashlib

        renewal = document_pdf("renewal")
        extracted = extract_document(renewal, "application/pdf")
        save_snapshot(
            db,
            case.id,
            "demo_renewal_source",
            {
                "document_id": "renewal",
                "sha256": hashlib.sha256(renewal).hexdigest(),
                "pages": extracted["pages"],
                "text": extracted["text"],
                "fictional": True,
                "verified_by": None,
                "source": "demo:renewal#page1",
            },
        )
        save_snapshot(db, case.id, "demo_documents", {"manifest": manifest(), "fictional": True})
        audit(db, case.id, "demo_showcase_created", f"broker:{user.id}", {"fictional": True})
    return status(db)


@router.get("/report.pdf")
def review_report(request: Request, db=Depends(database, scope="function")):
    import io
    from xml.sax.saxutils import escape
    from fastapi.responses import Response
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    demo_only()
    identity(db, request)
    data = status(db)
    if not data["case_id"]:
        raise DomainError("Create the showcase first", 409)
    styles = getSampleStyleSheet()
    stream = io.BytesIO()
    lines = [
        DISCLAIMER,
        "Fictional pilot review record",
        f"Case: {data['case_id']}",
        f"Document manifest: {data['manifest_hash']}",
        f"Review binding: {data['review_hash']}",
        f"G2 publication: {data['workflow_published']}. Audit chain verified: {data['chain_verified']}.",
        f"Demo review complete: {data['demo_ready']}. LIVE RELEASE APPROVED: FALSE.",
    ]
    lines.extend(f"Document: {d['title']} — SHA-256 {d['sha256']}" for d in data["documents"])
    lines.extend(f"Fictional reviewer: {r['name']}, {r['role']}, {r['at']}" for r in data["reviews"])
    if not data["reviews"]:
        lines.append("No demo reviewer decisions have been recorded.")
    story = []
    for line in lines:
        story.extend([Paragraph(escape(line), styles["BodyText"]), Spacer(1, 12)])
    SimpleDocTemplate(stream, title="Helm fictional pilot review record", author="Helm demonstration").build(
        story
    )
    return Response(
        stream.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="helm-demo-pilot-review.pdf"'},
    )


class DemoReview(Model):
    review_hash: str = Field(min_length=64, max_length=64)
    document_ids: list[str] = Field(max_length=20)
    acknowledgements: list[str] = Field(max_length=20)
    note: str = Field(min_length=20, max_length=2000)


@router.post("/reviews")
def review_showcase(body: DemoReview, request: Request, db=Depends(database, scope="function")):
    from app.auth.router import credential_access

    demo_only()
    user, proof = credential_access(db, request)
    if user.role not in {"compliance_officer", "legal_reviewer"}:
        raise DomainError("The demo compliance or legal reviewer must record this decision", 403)
    case = showcase_case(db)
    if not case:
        raise DomainError("Create the fictional showcase first", 409)
    case = service.get_case(db, case.id)
    current = status(db)
    if body.review_hash != current["review_hash"]:
        raise DomainError("Documents or advice changed. Review the current version.", 409)
    if not current["workflow_published"] or case.state not in {State.PUBLISHED, State.CLOSED}:
        raise DomainError(
            "Complete broker review and G2 publication before the pilot demonstration review", 409
        )
    if not current["chain_verified"]:
        raise DomainError("Audit integrity must be verified before review", 409)
    if (
        set(body.document_ids) != {d["id"] for d in current["documents"]}
        or set(body.acknowledgements) != set(CHECKLIST)
        or len(body.note.strip()) < 20
    ):
        raise DomainError("Review every document, confirm the demo scope and record a review note", 422)
    if any(r["user_id"] == user.id or r["role"] == user.role for r in current["reviews"]):
        raise DomainError("This reviewer role has already recorded a decision for this version", 409)
    save_snapshot(
        db,
        case.id,
        "demo_pilot_review",
        {
            "by": user.id,
            "role": user.role,
            "at": utcnow().isoformat(),
            "review_hash": body.review_hash,
            "note": body.note.strip(),
            "acknowledgements": body.acknowledgements,
            "fictional": True,
        },
    )
    db.add(
        Approval(
            case_id=case.id,
            gate="DEMO_P11",
            user_id=user.id,
            payload_hash=body.review_hash,
            step_up_at=utcnow().isoformat(),
        )
    )
    proof.consumed = True
    audit(
        db,
        case.id,
        "DEMO_REVIEW_RECORDED",
        f"user:{user.id}",
        {"role": user.role, "scope": "fictional_demo_only", "review_hash": body.review_hash},
    )
    db.flush()
    return status(db)
