import pytest

from app.policy_buying import BuyingStage, next_buying_stage
from app.schemas import DomainError, State


def test_policy_buying_reaches_issuance_in_the_specified_order():
    events = (
        "ipid_generated",
        "ipid_sent",
        "ipid_confirmed",
        "underwriting_approved",
        "banking_verified",
        "submission_sent",
        "policy_issued",
    )
    stage = BuyingStage.QUOTE_SELECTED
    visited = [stage]
    for event in events:
        stage = next_buying_stage(stage, event)
        visited.append(stage)
    assert visited == list(BuyingStage)


def test_consumer_ipid_query_returns_to_drafting_before_reconfirmation():
    stage = next_buying_stage("AWAITING_IPID_CONFIRMATION", "ipid_change_requested")
    assert stage == BuyingStage.IPID_DRAFTING
    with pytest.raises(DomainError):
        next_buying_stage(stage, "ipid_confirmed")
    stage = next_buying_stage(stage, "ipid_sent")
    assert next_buying_stage(stage, "ipid_confirmed") == BuyingStage.UNDERWRITING_IN_PROGRESS


@pytest.mark.parametrize(
    ("stage", "event"),
    [
        ("QUOTE_SELECTED", "policy_issued"),
        ("IPID_DRAFTING", "underwriting_approved"),
        ("UNDERWRITING_IN_PROGRESS", "submission_sent"),
        ("AWAITING_BANKING_DETAILS", "policy_issued"),
        ("SUBMISSION_PACKAGE_READY", "policy_issued"),
        ("POLICY_ISSUED", "ipid_generated"),
        ("POLICY_ISSUED", "policy_issued"),
        ("PUBLISHED", "ipid_generated"),
        ("CLOSED", "ipid_generated"),
        ("QUOTE_SELECTED", "unknown_event"),
        ("unknown_stage", "ipid_generated"),
    ],
)
def test_policy_buying_rejects_skipped_stages_and_terminal_reentry(stage, event):
    with pytest.raises(DomainError) as error:
        next_buying_stage(stage, event)
    assert error.value.status == 409


def test_recommendation_lifecycle_stays_separate():
    assert State.PUBLISHED == "PUBLISHED"
    assert State.CLOSED == "CLOSED"
    assert not set(BuyingStage) & set(State)


def test_unactioned_consumer_response_has_halt_priority():
    from datetime import datetime, timezone
    from app.copilot_projection import priority_score

    now = datetime(2026, 11, 4, tzinfo=timezone.utc)
    case = {
        "state": "PUBLISHED",
        "last_action_at": now.isoformat(),
        "coverage_type": "individual",
        "pending_consumer_response": True,
    }
    assert priority_score(case, now) == 100
    assert priority_score({**case, "state": "PAUSED_NEEDS_HUMAN"}, now) == 100
