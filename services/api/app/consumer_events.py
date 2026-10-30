"""Signed Core events record consumer choices; no policy is purchased by this service."""

import base64
import hashlib
import io
from datetime import date, timedelta
from typing import Literal
from pydantic import Field
from sqlalchemy import select
from app.db.models import Case, Job, Approval, utcnow
from app.db.store import latest, save_snapshot, audit
from app.schemas import DomainError, Model, State


class ConsumerEvent(Model):
    id: str = Field(min_length=1, max_length=100)
    type: Literal[
        "consumer.responded", "consumer.magic_link_opened", "consumer.magic_link_expired", "consumer.bound"
    ]
    case_id: str = Field(min_length=1, max_length=100)
    pack_hash: str = Field(min_length=64, max_length=64)
    decision: Literal["ACCEPTED", "DECLINED", "PARTIALLY"] | None = None
    selected_plan_id: str | None = Field(default=None, max_length=100)
    decline_reason: str = Field(default="", max_length=2000)
    partial_details: str = Field(default="", max_length=2000)
    opened_at: str | None = Field(default=None, max_length=50)
    plan_id: str | None = Field(default=None, max_length=100)
    policy_number: str | None = Field(default=None, max_length=100)
    effective_date: date | None = None


def closure_pdf(case, pack, outcome, approval, dnr):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from xml.sax.saxutils import escape

    stream = io.BytesIO()
    styles = getSampleStyleSheet()
    lines = [
        "Helm — fictional case closure",
        f"Case: {case.id}",
        f"Recorded: {utcnow().isoformat()}",
        f"Plan: {outcome.get('plan_id') or 'No binding recorded'}",
        f"G2 approved: {approval.created_at}",
        f"Broker reference: {approval.user_id}",
        f"Fact-find budget: GBP {dnr['needs']['budget_annual_pence'] / 100:.2f}",
        f"Priorities: {', '.join(dnr['needs']['priorities'])}",
        pack["suitability_final"],
        "Retention: proposed six-year review; legal/compliance policy approval remains pending.",
    ]
    lines.extend(
        f"Assessment: {r['plan_id']} — {r['stars']} stars — {r['decision']}"
        for r in pack.get("broker_ratings", [])
    )
    story = []
    for text in lines:
        story.extend([Paragraph(escape(text), styles["BodyText"]), Spacer(1, 12)])
    SimpleDocTemplate(stream).build(story)
    return stream.getvalue()


def handle(db, raw):
    event = ConsumerEvent.model_validate(raw)
    case = db.scalar(select(Case).where(Case.id == event.case_id).with_for_update())
    if not case:
        raise DomainError("Case not found", 404)
    pack_snapshot = latest(db, case.id, "pack")
    pack = pack_snapshot.body if pack_snapshot else {}
    if event.pack_hash != pack.get("pack_hash"):
        raise DomainError("Consumer event refers to an obsolete recommendation", 409)
    if case.state not in (State.PUBLISHED, State.CLOSED):
        raise DomainError("No delivered recommendation can accept this event", 409)
    previous = latest(db, case.id, "consumer_response")
    body = event.model_dump(mode="json")
    from app.service import transition

    if event.type == "consumer.responded":
        if case.state == State.CLOSED:
            raise DomainError("Case is closed", 409)
        if not event.decision:
            raise DomainError("Consumer decision is required", 422)
        if event.decision == "ACCEPTED" and event.selected_plan_id not in pack["selected"]:
            raise DomainError("Consumer selected a plan outside the approved recommendation", 422)
        if event.decision == "PARTIALLY" and not event.partial_details.strip():
            raise DomainError("Record the requested clarification", 422)
        if previous and previous.body["decision"] == "DECLINED":
            raise DomainError("The recommendation was already declined", 409)
        save_snapshot(db, case.id, "consumer_response", body)
        if event.decision == "DECLINED":
            transition(db, case, [case.state], State.CLOSED, "consumer_declined", "consumer")
    elif event.type == "consumer.bound":
        if case.state == State.CLOSED:
            raise DomainError("Binding already recorded or case closed", 409)
        if (
            not previous
            or previous.body["decision"] != "ACCEPTED"
            or event.plan_id != previous.body["selected_plan_id"]
        ):
            raise DomainError("Binding requires the matching consumer acceptance", 422)
        if not event.policy_number or not event.policy_number.strip() or not event.effective_date:
            raise DomainError("Binding reference and effective date are required", 422)
        plan = next(r["plan"] for r in pack["plans"] if r["plan"]["id"] == event.plan_id)
        body["final_premium"] = {
            "annual_pence": plan["annualPremiumPence"],
            "base_pence": plan["basePremiumPence"],
            "ipt_pence": plan["annualPremiumPence"] - plan["basePremiumPence"],
            "calculation_basis": "IPT included in annual premium; annual = base + IPT",
            "fictional_only": True,
        }
        save_snapshot(db, case.id, "policy_bound", body)
        transition(
            db, case, [case.state], State.CLOSED, "POLICY_BOUND", "consumer", {"plan_id": event.plan_id}
        )
    else:
        save_snapshot(db, case.id, "consumer_link", {"type": event.type, "at": utcnow().isoformat()})
    if case.state == State.CLOSED and event.type in {"consumer.bound", "consumer.responded"}:
        approval = db.scalar(
            select(Approval).where(
                Approval.case_id == case.id, Approval.gate == "G2", Approval.payload_hash == pack["pack_hash"]
            )
        )
        if not approval:
            raise DomainError("G2 evidence is missing", 409)
        content = closure_pdf(case, pack, body, approval, latest(db, case.id, "dnr").body)
        save_snapshot(
            db,
            case.id,
            "closure_pdf",
            {
                "base64": base64.b64encode(content).decode(),
                "sha256": hashlib.sha256(content).hexdigest(),
                "medical_included": False,
            },
        )
        save_snapshot(
            db, case.id, "plans_finalised", {"plan_ids": pack["selected"], "pack_hash": pack["pack_hash"]}
        )
        db.add(
            Job(
                case_id=case.id,
                kind="retention_review",
                due_at=(utcnow() + timedelta(days=6 * 365 + 2)).isoformat(),
                body={"requires_policy_approval": True, "proposed_years": 6},
            )
        )
    audit(
        db,
        case.id,
        event.type,
        "consumer",
        {
            "decision": event.decision,
            "plan_id": event.selected_plan_id or event.plan_id,
            "event_id": event.id,
        },
    )
    return case
