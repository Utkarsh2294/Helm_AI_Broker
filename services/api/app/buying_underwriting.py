"""Explicit seeded consumer completion, followed by a distinct broker decision."""

from app.db.models import stamp
from app.buying_review import current_document, set_document_state
from app.buying_updates import record_update
from app.schemas import DomainError
from app.policy_buying import next_buying_stage


def approve_declaration(db, case, buying, document_id, user, session):
    kind = "moratorium_declaration" if buying.underwriting_basis == "moratorium" else "fmu_questionnaire"
    document = current_document(db, buying, kind, document_id)
    response = buying.body.get("declaration_response") or {}
    statuses = buying.body["documents"]
    if not user.can_approve:
        raise DomainError("Broker approval authority is required", 403)
    if (
        buying.stage != "UNDERWRITING_IN_PROGRESS"
        or response.get("document_id") != document.id
        or statuses.get(kind, {}).get("status") != "returned"
        or any(statuses.get(key, {}).get("status") != "confirmed" for key in ("ipid", "toba"))
    ):
        raise DomainError("Current IPID, TOBA and explicitly completed declaration are required")
    if buying.underwriting_basis == "fmu":
        from app.medical_access import require_medical_access

        require_medical_access(db, case, user, session)
    set_document_state(buying, kind, document, "confirmed")
    buying.body = {**buying.body, "declaration_approved": stamp()}
    buying.stage = next_buying_stage(buying.stage, "underwriting_approved")
    from app.buying_banking import request_banking

    request_banking(db, buying)
    buying.pending_response = False
    record_update(
        db,
        buying,
        "declaration_approved",
        "Broker signed off the current consumer underwriting declaration",
        f"broker:{user.id}",
    )


def complete_declaration(db, buying, document_id, actor):
    kind = "moratorium_declaration" if buying.underwriting_basis == "moratorium" else "fmu_questionnaire"
    document = current_document(db, buying, kind, document_id)
    if (
        buying.stage != "UNDERWRITING_IN_PROGRESS"
        or buying.body["documents"].get(kind, {}).get("status") != "sent"
    ):
        raise DomainError("Send the current declaration before simulating a signature")
    if buying.underwriting_basis == "fmu":
        from app.db.policy_buying import BuyingMedicalResponse

        db.add(
            BuyingMedicalResponse(
                document_id=document.id,
                body={
                    "fictional": True,
                    "answers": {
                        "Personal details": "Demo patient, fictional details supplied afresh",
                        "GP practice": "Fictional Demo Practice — no real GP contact",
                        "Height and weight": "172 cm; 70 kg — fixture values",
                        "Smoking and alcohol": "Non-smoker; zero units — fixture values",
                        "Medical history entries": "Seeded fictional entry: resolved demo symptom in 2024; fictional consultation; no current fixture medication. Not a real medical history.",
                        "Family history": "Not required by this generic demo insurer",
                        "GP release consent": "Explicitly accepted in this simulation",
                        "Accuracy declaration": "I confirm the above information is complete and accurate to the best of my knowledge",
                    },
                    "signed_at": stamp(),
                },
            )
        )
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
        "Demo consumer completed and signed the current underwriting declaration; broker sign-off is required",
        actor,
    )
