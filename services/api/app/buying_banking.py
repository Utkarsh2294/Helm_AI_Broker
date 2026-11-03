"""Fictional fixtures only; raw financial values never enter document generation."""

from sqlalchemy import select
from app.db.policy_buying import BuyingBanking
from app.buying_documents import add_document
from app.buying_review import set_document_state, current_document
from app.buying_templates import WATERMARK, section
from app.buying_updates import record_update
from app.schemas import DomainError


def request_banking(db, buying):
    content = {
        "title": "Banking Details Request",
        "demo": True,
        "watermark": WATERMARK,
        "sections": [
            section(
                "Demo payment setup",
                "This demonstration never collects real banking details. The simulator supplies a dummy account holder, sort code and account number.",
            ),
            section(
                "Payment frequency",
                "Annual payment, matching the current IPID. Premiums would be paid directly to the insurer; Helm does not hold client money.",
            ),
            section(
                "Direct Debit mandate consent",
                "A separate explicit demo mandate acceptance is required. No bank is contacted and no live Direct Debit is created.",
            ),
        ],
    }
    document = add_document(db, buying, "banking_request", content)
    set_document_state(buying, "banking_request", document, "sent")
    buying.body = {
        **buying.body,
        "banking_request_id": document.id,
        "banking_received": False,
        "banking_verified": False,
    }
    record_update(
        db,
        buying,
        "banking_requested",
        "Banking request sent to the demo consumer automatically after broker underwriting approval",
    )


def complete_banking(db, buying, document_id, actor):
    document = current_document(db, buying, "banking_request", document_id)
    if (
        buying.stage != "AWAITING_BANKING_DETAILS"
        or not buying.body.get("declaration_approved")
        or buying.body.get("banking_received")
    ):
        raise DomainError("A current underwriting approval and outstanding banking request are required")
    # Only seeded data is accepted: there is no request field for arbitrary account numbers.
    row = BuyingBanking(
        request_document_id=document.id,
        body={
            "account_holder": "Fictional Demo Account",
            "sort_code": "000000",
            "account_number": "00001234",
            "payment_frequency": "annual",
            "mandate_consent": True,
            "fictional": True,
        },
    )
    db.add(row)
    db.flush()
    summary = add_document(
        db,
        buying,
        "banking_summary",
        {
            "title": "Banking Statement Information",
            "demo": True,
            "watermark": WATERMARK,
            "sections": [
                section(
                    "Payment setup",
                    "Fictional account holder: Fictional Demo Account. Account ending 1234; sort code masked. Annual payment to the fictional insurer; demo mandate consent explicitly accepted. No account verification with a bank took place.",
                )
            ],
        },
    )
    set_document_state(buying, "banking_request", document, "confirmed")
    set_document_state(buying, "banking_summary", summary, "draft")
    buying.body = {**buying.body, "banking_received": True}
    buying.pending_response = True
    record_update(
        db,
        buying,
        "banking_received",
        "Fictional banking details received; one-time broker verification is required",
        actor,
    )
