"""Demo policy-buying lifecycle, separate from the existing recommendation states.

The transactional service must validate permissions and document confirmations
before advancing; this graph only validates stage/event ordering.
"""

from enum import StrEnum

from app.schemas import DomainError


class BuyingStage(StrEnum):
    QUOTE_SELECTED = "QUOTE_SELECTED"
    IPID_DRAFTING = "IPID_DRAFTING"
    AWAITING_IPID_CONFIRMATION = "AWAITING_IPID_CONFIRMATION"
    UNDERWRITING_IN_PROGRESS = "UNDERWRITING_IN_PROGRESS"
    AWAITING_BANKING_DETAILS = "AWAITING_BANKING_DETAILS"
    SUBMISSION_PACKAGE_READY = "SUBMISSION_PACKAGE_READY"
    SUBMITTED_TO_INSURER = "SUBMITTED_TO_INSURER"
    POLICY_ISSUED = "POLICY_ISSUED"


TRANSITIONS = {
    (BuyingStage.QUOTE_SELECTED, "ipid_generated"): BuyingStage.IPID_DRAFTING,
    (BuyingStage.IPID_DRAFTING, "ipid_sent"): BuyingStage.AWAITING_IPID_CONFIRMATION,
    (BuyingStage.AWAITING_IPID_CONFIRMATION, "ipid_change_requested"): BuyingStage.IPID_DRAFTING,
    (BuyingStage.AWAITING_IPID_CONFIRMATION, "ipid_confirmed"): BuyingStage.UNDERWRITING_IN_PROGRESS,
    (BuyingStage.UNDERWRITING_IN_PROGRESS, "underwriting_approved"): BuyingStage.AWAITING_BANKING_DETAILS,
    (BuyingStage.AWAITING_BANKING_DETAILS, "banking_verified"): BuyingStage.SUBMISSION_PACKAGE_READY,
    (BuyingStage.SUBMISSION_PACKAGE_READY, "submission_sent"): BuyingStage.SUBMITTED_TO_INSURER,
    (BuyingStage.SUBMITTED_TO_INSURER, "policy_issued"): BuyingStage.POLICY_ISSUED,
}


def next_buying_stage(stage: str, event: str) -> BuyingStage:
    target = TRANSITIONS.get((stage, event))
    if target is None:
        raise DomainError("This policy-buying event is not available at the current stage")
    return target
