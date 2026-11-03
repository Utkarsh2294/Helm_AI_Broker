"""Fictional fixtures only; raw financial values never enter document generation."""

from sqlalchemy import select
from app.db.policy_buying import BuyingBanking
from app.buying_documents import add_document
from app.buying_review import set_document_state, current_document
from app.buying_templates import WATERMARK, section
from app.buying_updates import record_update
from app.schemas import DomainError
from app.db.models import stamp
from app.policy_buying import next_buying_stage


def banking_record(db, buying):
    row = db.scalar(
        select(BuyingBanking)
        .where(BuyingBanking.request_document_id == buying.body.get("banking_request_id"))
        .with_for_update()
    )
    if not row or not buying.body.get("banking_received") or buying.stage != "AWAITING_BANKING_DETAILS":
        raise DomainError("No current banking response is awaiting verification")
    return row


def reveal_banking(db, buying, actor):
    row = banking_record(db, buying)
    if row.revealed_at:
        raise DomainError("This fictional account has already been revealed once; use its masked summary")
    row.revealed_at = stamp()
    record_update(
        db,
        buying,
        "banking_revealed",
        "Broker used the one-time fictional banking verification screen",
        actor,
    )
    return row.body


def verify_banking(db, buying, actor):
    row = banking_record(db, buying)
    if not row.revealed_at:
        raise DomainError("Use the one-time verification screen before confirming banking")
    buying.body = {**buying.body, "banking_verified": True}
    buying.stage = next_buying_stage(buying.stage, "banking_verified")
    buying.pending_response = False
    from app.buying_documents import current_documents

    summary = current_documents(db, buying.id)["banking_summary"]
    set_document_state(buying, "banking_summary", summary, "confirmed")
    from app.buying_submission import prepare_package
    from app.db.models import Case

    prepare_package(db, db.get(Case, buying.case_id), buying)
    record_update(
        db,
        buying,
        "banking_verified",
        "Broker verified the fictional annual payment setup; no bank was contacted",
        actor,
    )


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
