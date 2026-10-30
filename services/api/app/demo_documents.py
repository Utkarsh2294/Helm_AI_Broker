"""Fictional document fixtures for demonstrating the whole broker/pilot journey."""

import hashlib
from functools import lru_cache
import io
from xml.sax.saxutils import escape
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from app.auth import identity
from app.config import settings
from app.schemas import DomainError

router = APIRouter(prefix="/api/v1/demo")
DISCLAIMER = "DEMONSTRATION ONLY — FICTIONAL DATA. NOT LEGAL, REGULATORY OR INSURER APPROVAL."
DOCUMENTS = {
    "renewal": (
        "Fictional policy renewal",
        "P3: document intake",
        [
            "Applicant: Morgan Demo. Request reference: DEMO-PILOT-001.",
            "Current fictional provider: Northgate. Renewal annual premium GBP 1,344.00, including IPT GBP 144.00. Excess GBP 250.00.",
            "Stated request: individual PMI, cancer level 3, mental health level 2, outpatient level 3, hospital list level 2. Annual budget GBP 1,800.00.",
            "This fixture contains no medical history. A broker checks every extracted fact before G0. No inference about cover is authorised.",
        ],
    ),
    "ipid": (
        "Sample product information document",
        "P5–P6: product and suitability review",
        [
            "Northgate Sample PMI — IPID fixture v2026-10. It is a comparison aid, not an offer or contract.",
            "Example benefits: requested cancer, outpatient and mental-health levels are shown in each returned structured quote. Check that specific plan's terms, limits and excess.",
            "Significant limitations: underwriting applies. No statement here confirms whether any medical condition is covered. Review insurer terms and ask the underwriter where necessary.",
            "Documents: identity evidence and current policy schedule may be required. The insurer determines actual underwriting and acceptance.",
            "Cancellation example: 14-day notice wording requires compliance approval and must reflect when the contract and its terms were received. No real cancellation right is determined by this fixture.",
        ],
    ),
    "toba": (
        "Sample terms of business and panel",
        "P4: partner release",
        [
            "Fictional entity: Helm Demonstration Brokerage. Reference DEMO-FRN-000 — not an FCA registration.",
            "Five fictional providers: Northgate Health, Cedar Mutual, ClearPath Insurance, MediFirst UK and PremiumCare. This is a panel search, not a whole-market claim.",
            "Only partners with active demo terms and authorised fixture status receive a minimised RFQ after G0/G1. Names and medical wording are excluded from the default RFQ.",
            "Remuneration: example commission is disclosed separately and cannot enter ranking scores. Premiums are paid directly to an insurer; this portal does not hold client money.",
            "A broker approves every recommendation. This document grants no real agency, insurer agreement or payment authority.",
        ],
    ),
    "dpia": (
        "Demonstration DPIA and data flows",
        "P10: privacy review",
        [
            "Scope: fictional requests only. Controller: Helm Demonstration Brokerage, a fictional organisation. No live lawful basis or special-category consent is established by this document.",
            "Flow: signed Core fixture to encrypted request/DNR; minimised requirements to local agent steps; structured RFQ to fictional partner simulator; immutable broker-approved pack to MockCore.",
            "Medical wording stays encrypted locally. External model calls default off; no provider region or transfer approval is implied. Only allow-listed non-medical fields may enter an approved gateway.",
            "Retention example: proposed six-year review after closure. The source plan also says seven years. A policy owner must resolve that conflict; holds prevent erasure. No destructive job is enabled by this fixture.",
            "Rights rehearsal: verify identity, find the case, export scoped/redacted evidence, record the request, consult the policy owner and check a legal hold before any deletion. Do not email unprotected health records.",
            "Unresolved risk: upstream dependency/image advisories, real OCR and representative evaluations, production recovery/keys, manual accessibility and independent security acceptance. Demo review does not remove these risks.",
        ],
    ),
    "register": (
        "Fictional pilot broker register",
        "P11: onboarding",
        [
            "Garv Gupta — broker@helm.demo — adviser persona — DEMO-IRN. James Thornton — lead@helm.demo — lead adviser persona — DEMO-IRN.",
            "Taylor Demo — pilot@helm.demo — third adviser persona — DEMO-IRN. All references are explicitly fictional and were not checked against the FCA Register.",
            "Sam Taylor — compliance@helm.demo — compliance reviewer persona. Casey Demo — legal@helm.demo — legal reviewer persona. Distinct accounts record separate demo decisions.",
            "Onboarding: sign in with the demo credentials shown in the operating guide, register a passkey after re-authentication, sign out/in, open the assigned fictional case and review its evidence.",
            "Live accounts require owner-supplied identity, verified authority and secure invitation delivery. No real onboarding email is sent.",
        ],
    ),
    "runbook": (
        "Pilot demonstration runbook",
        "P11: operational rehearsal",
        [
            "Start the local preview or seven-service Compose stack. Preserve the data/key volumes. Readiness requires both database and Redis checks to succeed.",
            "Walkthrough: create the showcase, review the renewal and DNR, sign G0, release G1, compare all five plans, rate each, select/order three, confirm suitability, re-authenticate and approve G2.",
            "Inspect audit/evidence PDF, trigger a signed consumer response, demonstrate complaint hold and owner resolution, and run a bounded learning proposal with two independent G5 decisions.",
            "Recovery rehearsal: back up data and encryption keys together; restore to an isolated database; verify all case chains and approved pack hashes. Never test restore by overwriting the working demo.",
            "Incident: pause agents, preserve evidence, revoke affected sessions, record the decision and escalate to the owner. A demo review never authorises processing real cases.",
        ],
    ),
    "go-no-go": (
        "Demonstration go/no-go review",
        "P11: separate reviewer decisions",
        [
            "Decision scope: demonstrate the user journey with fictional data only. It is never permission to launch a real-customer pilot.",
            "Review the six supporting documents, the actual test/security evidence and a published fictional case. The compliance and legal personas each re-authenticate and record their own decision.",
            "Required demo evidence: current document manifest hash, completed broker review/publication, checklist acknowledgements and two distinct reviewers. Any revision requires a new review.",
            "Live decision: NO GO until real legal/FCA/DPO/compliance identities, production infrastructure, integration contracts and outstanding security/accessibility/performance acceptance are supplied and accepted.",
        ],
    ),
}


def database():
    from app.main import database as dependency

    yield from dependency()


def demo_only():
    if settings().clock_mode != "demo":
        raise DomainError("Demonstration fixtures are unavailable in live mode", 404)


@lru_cache(maxsize=7)
def document_pdf(document_id):
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    if document_id not in DOCUMENTS:
        raise DomainError("Demo document not found", 404)
    title, stage, paragraphs = DOCUMENTS[document_id]
    stream = io.BytesIO()
    styles = getSampleStyleSheet()
    story = [
        Paragraph(escape(title), styles["Title"]),
        Spacer(1, 16),
        Paragraph(escape(DISCLAIMER), styles["Heading2"]),
        Paragraph(escape(stage), styles["BodyText"]),
        Spacer(1, 14),
    ]
    for text in paragraphs:
        story.extend([Paragraph(escape(text), styles["BodyText"]), Spacer(1, 12)])

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.drawString(42, 24, "Helm fictional showcase | v1 | no real customer processing")
        canvas.drawRightString(550, 24, str(doc.page))
        canvas.restoreState()

    SimpleDocTemplate(stream, title=title, author="Helm fictional showcase", invariant=1).build(
        story, onFirstPage=footer, onLaterPages=footer
    )
    return stream.getvalue()


def manifest():
    return [
        {
            "id": key,
            "title": title,
            "stage": stage,
            "sha256": hashlib.sha256(document_pdf(key)).hexdigest(),
            "url": f"/api/v1/demo/documents/{key}.pdf",
        }
        for key, (title, stage, _) in DOCUMENTS.items()
    ]


@router.get("/documents")
def documents(request: Request, db=Depends(database, scope="function")):
    demo_only()
    identity(db, request)
    from app.agents.review import canonical_hash

    items = manifest()
    return {
        "fictional": True,
        "disclaimer": DISCLAIMER,
        "items": items,
        "manifest_hash": canonical_hash(items),
        "live_release_approved": False,
    }


@router.get("/documents/{document_id}.pdf")
def download_document(document_id: str, request: Request, db=Depends(database, scope="function")):
    demo_only()
    identity(db, request)
    content = document_pdf(document_id)
    return Response(
        content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="helm-demo-{document_id}.pdf"',
            "X-Content-SHA256": hashlib.sha256(content).hexdigest(),
        },
    )
