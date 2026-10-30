"""Signed consumer messages stay encrypted and route dissatisfaction to people."""

from typing import Literal
from pydantic import Field
from app.db.store import save_snapshot, audit
from app.schemas import Model, DomainError


class ConsumerMessage(Model):
    id: str = Field(min_length=1, max_length=100)
    type: Literal["consumer.message_received"]
    case_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=4000)
    possible_complaint: bool = False


def handle(db, raw):
    from app import service
    from app.compliance.medical_firewall import possible_complaint
    from app.complaints import open_complaint

    event = ConsumerMessage.model_validate(raw)
    if not event.text.strip():
        raise DomainError("Consumer message is empty", 422)
    case = service.get_case(db, event.case_id)
    flagged = event.possible_complaint or possible_complaint(event.text)
    save_snapshot(
        db,
        case.id,
        "consumer_message",
        {"event_id": event.id, "text": event.text, "possible_complaint": flagged},
    )
    if flagged:
        open_complaint(db, case, "consumer", event.text)
    audit(
        db,
        case.id,
        "consumer_message_received",
        "consumer",
        {"event_id": event.id, "possible_complaint": flagged, "automatic_reply_sent": False},
    )
    return case
