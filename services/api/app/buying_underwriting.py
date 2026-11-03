"""Explicit seeded consumer completion, followed by a distinct broker decision."""

from app.db.models import stamp
from app.buying_review import current_document, set_document_state
from app.buying_updates import record_update
from app.schemas import DomainError


def complete_declaration(db, buying, document_id, actor):
    kind = "moratorium_declaration" if buying.underwriting_basis == "moratorium" else "fmu_questionnaire"
    document = current_document(db, buying, kind, document_id)
    if (
        buying.stage != "UNDERWRITING_IN_PROGRESS"
        or buying.body["documents"].get(kind, {}).get("status") != "sent"
    ):
        raise DomainError("Send the current declaration before simulating a signature")
    if buying.underwriting_basis != "moratorium":
        raise DomainError("Use the seeded FMU questionnaire completion path", 422)
    buying.body = {
        **buying.body,
        "declaration_response": {"document_id": document.id, "signed_at": stamp(), "fictional": True},
    }
    set_document_state(buying, kind, document, "returned")
    buying.pending_response = True
    record_update(
        db,
        buying,
        "declaration_completed",
        "Demo consumer explicitly accepted the Moratorium Declaration; broker sign-off is required",
        actor,
    )
