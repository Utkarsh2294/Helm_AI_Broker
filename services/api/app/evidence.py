"""Fourteen-section evidence exports and historical snapshots from immutable records."""
import io
import json
from datetime import timezone
from xml.sax.saxutils import escape
from sqlalchemy import select
from app.agents.review import canonical_hash
from app.compliance.medical_firewall import safe_case
from app.db.models import Activity, Approval, Snapshot, utcnow
from app.db.store import verify_chain
from app.schemas import DomainError

CONTROLS = {
    "C1": "DNR sign-off before RFQ", "C2": "Suitability checklist", "C3": "Personalised explanations",
    "C4": "Record keeping", "C5": "Versioned IPIDs", "C6": "Cancellation notice",
    "C7": "Premium and IPT arithmetic", "C8": "Remuneration disclosure", "C9": "Terms of business",
    "C10": "Search basis", "C11": "Consumer Duty and readable explanations", "C12": "Vulnerability routing",
    "C13": "Complaint handling", "C14": "Special-category information firewall", "C15": "LLM provider transfer controls",
    "C16": "No client money", "C17": "FCA adviser authorisation", "C18": "Immutable audit evidence",
}


def generate(db, case, user, include_medical=False):
    snapshots = db.scalars(select(Snapshot).where(Snapshot.case_id == case.id).order_by(Snapshot.created_at, Snapshot.version)).all()
    events = db.scalars(select(Activity).where(Activity.case_id == case.id).order_by(Activity.seq)).all()
    approvals = db.scalars(select(Approval).where(Approval.case_id == case.id)).all()
    last = {s.kind: s.body for s in snapshots}
    pack = last.get("pack", {})
    sections = {
        "case_summary": {"case_id": case.id, "consumer_ref": case.core_request_id, "cover_type": case.profile["cover_type"], "state": case.state, "assigned_broker": case.assigned_to, "created_at": case.created_at},
        "dnr_versions": [{"version": s.version, "body_hash": s.body_hash, "created_at": s.created_at, "body": s.body} for s in snapshots if s.kind == "dnr"],
        "demands_and_needs_record": last.get("dnr"),
        "rfq_record": last.get("rfq"),
        "raw_partner_messages": last.get("quotes", {}).get("partners", []),
        "canonical_quotes": [{"version": s.version, "canonical": s.body.get("quotes", []), "raw_quotes": s.body.get("raw_quotes", [])} for s in snapshots if s.kind == "quotes"],
        "ranking_snapshot": last.get("ranking"),
        "survey": last.get("selection", {}).get("survey"),
        "suitability_statement": {"draft_text": pack.get("suitability_draft"), "final_text": pack.get("suitability_final"), "diff": pack.get("suitability_diff", [])},
        "quote_pack": pack or None,
        "approvals": [{k: getattr(a, k) for k in ("id", "gate", "user_id", "payload_hash", "step_up_at", "created_at")} for a in approvals],
        "publication": last.get("publication"),
        "audit_chain": {"verified": verify_chain(events), "chain_length": len(events), "last_hash": events[-1].hash if events else None, "verification_timestamp": utcnow().isoformat(),
                        "events": [{k: getattr(e, k) for k in ("seq", "actor", "type", "payload", "created_at", "prev_hash", "hash")} for e in events]},
        "compliance_checklist": [{"control": key, "description": description, "evidence": control_evidence(key, pack, last, approvals, events)} for key, description in CONTROLS.items()],
    }
    result = safe_case(sections, user, include_medical)
    return {**result, "exported_at": utcnow().isoformat(), "exported_by": user.name, "pack_hash": canonical_hash(result)}


def control_evidence(control, pack, last, approvals, events):
    mapping = {"C1": "dnr", "C2": "pack", "C3": "pack", "C4": "dnr", "C5": "pack", "C6": "pack", "C7": "pack", "C8": "pack", "C9": "pack", "C10": "pack", "C11": "ranking", "C12": "dnr", "C14": "dnr"}
    if control == "C13":
        return {"recorded": any(e.type == "complaint_flagged" for e in events), "reference": "audit_chain", "applicability": "if_complaint_received"}
    if control in ("C15", "C16"):
        return {"recorded": False, "reference": "deployment_control_review", "status": "release_review_required"}
    if control == "C17":
        return {"recorded": any(a.gate == "G2" for a in approvals), "reference": "approvals"}
    if control == "C18":
        return {"recorded": bool(events), "verified": verify_chain(events), "reference": "audit_chain"}
    kind = mapping[control]
    return {"recorded": bool(last.get(kind)), "reference": kind, "legal_signoff": "pending" if control in {"C5", "C6", "C8", "C9", "C10"} else "not_applicable"}


def pdf_bytes(data):
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
    stream = io.BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="EvidenceBody", fontName="Helvetica", fontSize=9, leading=13, alignment=TA_LEFT, textColor=colors.HexColor("#24342e"), wordWrap="CJK"))
    story = [Paragraph("HELM / BROKER", styles["Title"]), Spacer(1, 28), Paragraph("Evidence Package", styles["Heading1"]),
             Paragraph("Fictional prototype records", styles["Heading2"])]
    for text in (data["case_summary"]["case_id"], data["exported_at"], "Exported by " + data["exported_by"], "Content SHA-256: " + data["pack_hash"]):
        story.extend([Spacer(1, 10), Paragraph(escape(text), styles["EvidenceBody"])])
    section_keys = list(data)[:14]
    for i, key in enumerate(section_keys, 1):
        story.extend([PageBreak(), Paragraph(f"{i:02d} / {key.replace('_', ' ').title()}", styles["Heading1"]), Spacer(1, 12)])
        # Small paragraphs wrap long identifiers and let ReportLab paginate large audit sets.
        for line in json.dumps(data[key], indent=2, ensure_ascii=False).splitlines():
            story.append(Paragraph(escape(line) or "&#160;", styles["EvidenceBody"]))
    def footer(canvas, doc):
        canvas.setFont("Helvetica", 8)
        canvas.drawString(42, 25, "Helm Broker · Fictional prototype · Controlled evidence export")
        canvas.drawRightString(A4[0] - 42, 25, str(doc.page))
    SimpleDocTemplate(stream, pagesize=A4, rightMargin=42, leftMargin=42, topMargin=42, bottomMargin=45).build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()


def replay(db, case, at, user):
    at = at.astimezone(timezone.utc).isoformat()
    if at < case.created_at:
        raise DomainError("This case did not exist at the requested time", 404)
    events = db.scalars(select(Activity).where(Activity.case_id == case.id, Activity.created_at <= at).order_by(Activity.seq)).all()
    snapshots = db.scalars(select(Snapshot).where(Snapshot.case_id == case.id, Snapshot.created_at <= at).order_by(Snapshot.created_at, Snapshot.version)).all()
    state = "RECEIVED"
    for e in events:
        state = e.payload.get("to", state)
    result = {"id": case.id, **case.profile, "state": state, "created_at": case.created_at, "historical": True, "as_of": at,
              "assigned_to": None, "events": [{k: getattr(e, k) for k in ("seq", "actor", "type", "payload", "created_at", "hash")} for e in events],
              **dict.fromkeys(("dnr", "rfq", "quotes", "ranking", "pack", "publication"))}
    for s in snapshots:
        if s.kind in result:
            result[s.kind] = s.body
    return safe_case(result, user)
