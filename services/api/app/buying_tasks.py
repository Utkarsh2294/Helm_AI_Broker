"""Deterministic buying cards reuse the broker rail and its existing snoozes."""

from datetime import datetime
from sqlalchemy import select
from app.db.models import Case, utcnow
from app.db.policy_buying import BuyingCase
from app.db.copilot import TaskSnooze
from app.case_access import visible_cases


def task_cards(db, user, broker_id=None, include_snoozed=False, case_id=None):
    from app.copilot_api import metric_scope
    from app.copilot_projection import priority_score

    scope = metric_scope(user, broker_id, model=Case)
    rows = db.execute(
        select(BuyingCase, Case)
        .join(Case, Case.id == BuyingCase.case_id)
        .where(
            scope,
            visible_cases(user),
            BuyingCase.closed_at.is_(None),
            Case.state == "PUBLISHED",
            BuyingCase.case_id == case_id if case_id else True,
        )
    ).all()
    now = utcnow()
    tasks = []
    for buying, case in rows:
        if buying.stage == "IPID_DRAFTING":
            key, title, step = "review_ipid_response", "Review the IPID draft or consumer change", "ipid"
        elif buying.stage == "UNDERWRITING_IN_PROGRESS":
            key, title, step = (
                "review_declaration",
                "Review TOBA and the underwriting declaration",
                "underwriting",
            )
        elif buying.stage == "SUBMISSION_PACKAGE_READY":
            key, title, step = (
                "review_submission_package",
                "Review and send the demo submission package",
                "submission",
            )
        elif buying.stage == "AWAITING_BANKING_DETAILS" and buying.pending_response:
            key, title, step = "review_submission_package", "Verify the fictional banking setup", "banking"
        else:
            continue
        snooze = db.get(TaskSnooze, (user.id, case.id, key))
        if not include_snoozed and snooze and snooze.snoozed_until > now.isoformat():
            continue
        days = max(0, (now - datetime.fromisoformat(buying.updated_at)).days)
        score = priority_score(
            {
                "state": case.state,
                "coverage_type": case.profile.get("cover_type", "individual"),
                "last_action_at": buying.updated_at,
                "pending_consumer_response": buying.pending_response,
            },
            now,
        )
        tasks.append(
            {
                "case_id": case.id,
                "task_key": key,
                "type": key,
                "title": title,
                "state": buying.stage,
                "client": "Saved case",
                "priority_score": score,
                "base_priority_score": score,
                "last_action_at": buying.updated_at,
                "overdue": days >= 5,
                "elapsed_days": days,
                "sla_days": 5,
                "total": 0,
                "rated": 0,
                "halt_code": None,
                "source": f"pb_update_feed:{buying.id}:{buying.version}",
                "href": f"/policy-buying/cases/{case.id}?step={step}",
                "estimated_minutes": None,
                "snoozed_until": snooze.snoozed_until if snooze else None,
            }
        )
    return tasks
