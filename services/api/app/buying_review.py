"""Version-bound broker edits and document delivery; no model sees submitted answers."""

import copy
import re
from app.buying_documents import current_documents, add_document
from app.buying_updates import record_update
from app.schemas import DomainError
from app.policy_buying import BuyingStage, next_buying_stage

EDITABLE = {"ipid", "toba", "moratorium_declaration", "fmu_questionnaire"}


def consumer_response(db, buying, kind, document_id, decision, note, actor):
    document = current_document(db, buying, kind, document_id)
    if kind not in {"ipid", "toba"}:
        raise DomainError("Use the separate signed underwriting completion action", 422)
    if buying.body.get("documents", {}).get(kind, {}).get("status") != "sent":
        raise DomainError("Only a sent document can receive a consumer response")
    if decision == "change":
        if kind != "ipid" or not note.strip():
            raise DomainError("The consumer can query the IPID; TOBA is the broker's statement", 422)
        buying.stage = next_buying_stage(buying.stage, "ipid_change_requested")
        set_document_state(buying, kind, document, "change_requested")
        buying.body = {**buying.body, "consumer_query": note.strip()}
        buying.pending_response = True
        message = "Demo consumer requested an IPID correction; broker review is required"
    else:
        set_document_state(buying, kind, document, "confirmed")
        if kind == "ipid":
            buying.stage = next_buying_stage(buying.stage, "ipid_confirmed")
            from app.buying_agreements import accepted

            terms = current_documents(db, buying.id).get("toba")
            prior = accepted(db, buying, terms) if terms else None
            if prior:
                set_document_state(buying, "toba", terms, "confirmed")
                buying.body = {**buying.body, "standing_toba_acceptance": prior.id}
                record_update(
                    db,
                    buying,
                    "standing_toba_reused",
                    "Unchanged standing terms were already acknowledged by this demo consumer; no new signature was inferred",
                    actor,
                )
        elif kind == "toba":
            from app.buying_agreements import record_acceptance

            record_acceptance(db, buying, document)
        buying.pending_response = False
        buying.body = {**buying.body, "consumer_query": None}
        message = f"Demo consumer acknowledged the current {kind.upper()} version"
    record_update(
        db,
        buying,
        "consumer_responded",
        message,
        actor,
        document_id=document.id,
        document_version=document.version,
    )


def set_document_state(buying, kind, document, status):
    buying.body = {
        **buying.body,
        "documents": {**buying.body.get("documents", {}), kind: {"id": document.id, "status": status}},
    }


def current_document(db, buying, kind, document_id):
    document = current_documents(db, buying.id).get(kind)
    if not document or document.id != document_id:
        raise DomainError("The document version changed. Review the current draft")
    return document


def revise_document(db, buying, kind, document_id, sections, instruction, actor):
    if kind not in EDITABLE:
        raise DomainError("This generated record cannot be edited", 422)
    previous = current_document(db, buying, kind, document_id)
    content = copy.deepcopy(previous.content)
    if instruction:
        # shortcut: local demo supports explicit section rewrites; arbitrary AI editing needs an approved model.
        match = re.fullmatch(r"section\s+(.+?):\s*(.+)", instruction.strip(), re.I | re.S)
        target = next(
            (
                row
                for row in content["sections"]
                if match and row["heading"].casefold() == match[1].strip().casefold()
            ),
            None,
        )
        if not target:
            raise DomainError(
                'Local demo: use "Section <heading>: <replacement wording>" or Edit manually', 422
            )
        target["text"] = match[2].strip()
    else:
        if [row["heading"] for row in sections] != [row["heading"] for row in content["sections"]]:
            raise DomainError("Keep every required section and its heading", 422)
        content["sections"] = sections
    if kind == "ipid":
        from app.buying_pdf import build_pdf

        build_pdf(content, kind)
    document = add_document(db, buying, kind, content, actor, edited=not bool(instruction))
    # Any revision invalidates downstream consumer confirmations and package readiness.
    order = [
        "ipid",
        "toba",
        "moratorium_declaration",
        "fmu_questionnaire",
        "banking_summary",
        "submission_package",
    ]
    states = dict(buying.body.get("documents", {}))
    for name in order[order.index(kind) :]:
        if name in states:
            states[name] = {"id": states[name]["id"], "status": "draft"}
    buying.body = {
        **buying.body,
        "documents": states,
        "declaration_response": None,
        "declaration_approved": False,
        "banking_verified": False,
        "submission_reviewed": None,
    }
    set_document_state(buying, kind, document, "draft")
    buying.stage = BuyingStage.IPID_DRAFTING if kind == "ipid" else BuyingStage.UNDERWRITING_IN_PROGRESS
    buying.pending_response = False
    record_update(
        db,
        buying,
        "broker_edit",
        f"Broker saved a new {kind.replace('_', ' ')} version; affected confirmations must be repeated",
        actor,
    )
    return document


def send_document(db, buying, kind, document_id, actor):
    document = current_document(db, buying, kind, document_id)
    if kind not in EDITABLE or not buying.body.get("baseline_acknowledged"):
        raise DomainError("Acknowledge the underwriting baseline before sending documents")
    if buying.body.get("documents", {}).get(kind, {}).get("status") != "draft":
        raise DomainError("Only the current draft can be approved and sent")
    if kind == "ipid":
        buying.stage = next_buying_stage(buying.stage, "ipid_sent")
    else:
        if (
            buying.stage != "UNDERWRITING_IN_PROGRESS"
            or buying.body["documents"].get("ipid", {}).get("status") != "confirmed"
        ):
            raise DomainError("The consumer must confirm the current IPID first")
        if kind != "toba" and buying.body["documents"].get("toba", {}).get("status") != "confirmed":
            raise DomainError("The TOBA must be acknowledged before the declaration is sent")
    set_document_state(buying, kind, document, "sent")
    record_update(
        db,
        buying,
        "document_sent",
        f"{kind.replace('_', ' ').title()} approved and sent to the demo consumer",
        actor,
    )
