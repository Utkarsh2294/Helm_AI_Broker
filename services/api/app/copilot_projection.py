"""Transactional, non-clinical projections. No model decides tasks or priorities."""

import json
import hashlib
from collections import defaultdict
from datetime import datetime
from sqlalchemy import select, delete, text, func, cast, DateTime, Integer, case as sql_case
from app.db.models import Activity, Case, Snapshot, User, utcnow
from app.db.platform import BrokerRating
from app.db.copilot import CaseMetric, ProviderMetric, CaseSatisfaction, Notification

FINISHED = {"PUBLISHED", "CLOSED"}
SLA_DAYS = {"individual": 5, "couple": 5, "family": 5}


def priority_score(case, now):
    """WA §10.8 formula, with an explicit clock for reproducible results."""
    elapsed = max(0, (now - datetime.fromisoformat(case["last_action_at"])).days)
    fraction = elapsed / SLA_DAYS.get(case["coverage_type"], 5)
    score = (
        100 if case["state"] == "PAUSED_NEEDS_HUMAN" or case.get("pending_consumer_response") else 0
    ) + fraction * 50
    if fraction >= 1:
        score += 200
    if case["state"] in {"BROKER_REVIEW", "AWAITING_BROKER_REVIEW"}:
        score += 30 * (1 - case.get("unrated_plan_fraction", 1))
    return score


def priority_expression(dialect, now):
    """SQL equivalent for cursor-paginated queues; the cursor freezes the clock."""
    from app.db.policy_buying import BuyingCase

    pending = (
        select(BuyingCase.id)
        .where(
            BuyingCase.case_id == Case.id,
            BuyingCase.pending_response.is_(True),
            BuyingCase.closed_at.is_(None),
        )
        .exists()
    )
    last = func.coalesce(CaseMetric.last_action_at, Case.created_at)
    if dialect == "postgresql":
        elapsed = func.greatest(
            0, func.floor(func.extract("epoch", now - cast(last, DateTime(timezone=True))) / 86400)
        )
        least = func.least
    else:
        elapsed = func.max(0, cast(func.julianday(now.isoformat()) - func.julianday(last), Integer))
        least = func.min
    fraction = elapsed / 5.0
    total = func.coalesce(CaseMetric.body["plans"].as_integer(), 0)
    rated = func.coalesce(CaseMetric.body["rated"].as_integer(), 0)
    rated_fraction = sql_case((total > 0, least(rated, total) * 1.0 / func.nullif(total, 0)), else_=0)
    return (
        sql_case(((Case.state == "PAUSED_NEEDS_HUMAN") | pending, 100), else_=0)
        + fraction * 50
        + sql_case((fraction >= 1, 200), else_=0)
        + sql_case(
            (Case.state.in_(["BROKER_REVIEW", "AWAITING_BROKER_REVIEW"]), 30 * rated_fraction), else_=0
        )
        + func.coalesce(CaseMetric.body["priority_boost"].as_float(), 0)
    )


def project_case(db, case):
    snapshots = db.scalars(
        select(Snapshot).where(Snapshot.case_id == case.id).order_by(Snapshot.version)
    ).all()
    saved = {row.kind: row.body for row in snapshots}
    dnr, ranking = saved.get("dnr", {}), saved.get("ranking", {})
    needs = dnr.get("needs", saved.get("request", {}).get("needs", {}))
    top = ranking.get("top", [])
    quotes = saved.get("quotes", {}).get("quotes", [])
    chosen = saved.get("selection", {}).get("selected", saved.get("pack", {}).get("selected", []))
    events = db.scalars(select(Activity).where(Activity.case_id == case.id).order_by(Activity.seq)).all()
    actions = [e.created_at for e in events if e.actor.startswith(("broker:", "user:"))]
    closed = next((e.created_at for e in events if e.payload.get("to") in FINISHED), None)
    ratings = db.scalars(
        select(BrokerRating)
        .where(BrokerRating.case_id == case.id, BrokerRating.ranking_id == ranking.get("id", ""))
        .order_by(BrokerRating.version)
    ).all()
    ratings = {r.plan_id: r for r in ratings}
    survey = db.scalars(
        select(CaseSatisfaction)
        .where(CaseSatisfaction.case_id == case.id)
        .order_by(CaseSatisfaction.submitted_at)
    ).all()
    by_state = defaultdict(float)
    previous, entered = "RECEIVED", case.created_at
    for event in events:
        if event.payload.get("to"):
            by_state[previous] += (
                max(
                    0,
                    (
                        datetime.fromisoformat(event.created_at) - datetime.fromisoformat(entered)
                    ).total_seconds(),
                )
                / 86400
            )
            previous, entered = event.payload["to"], event.created_at
    plans = {p.get("id"): p for p in quotes}
    plans.update({r.get("plan", {}).get("id"): r.get("plan", {}) for r in top})
    first = plans.get(chosen[0], {}) if chosen else {}
    metric = db.get(CaseMetric, case.id)
    if not metric:
        metric = CaseMetric(case_id=case.id)
        db.add(metric)
    metric.broker_id, metric.coverage_type, metric.state = (
        case.assigned_to,
        case.profile.get("cover_type", "individual"),
        case.state,
    )
    metric.created_at, metric.closed_at = case.created_at, closed
    metric.last_action_at = max(actions) if actions else case.created_at
    metric.insurer_id = first.get("insurerId")
    metric.budget_pence = needs.get("budget_annual_pence")
    metric.close_days = (
        max(0, (datetime.fromisoformat(closed) - datetime.fromisoformat(case.created_at)).total_seconds())
        / 86400
        if closed
        else None
    )
    metric.csat = survey[-1].score if survey else None
    metric.updated_at = utcnow().isoformat()
    previous_signal = (metric.body or {}).get("aging_signal")
    valid_signal = bool(
        previous_signal
        and previous_signal["state"] == case.state
        and previous_signal.get("state_entered_at") == entered
    )
    metric.body = {
        "aging_signal": previous_signal if valid_signal else None,
        "priority_boost": 25 if valid_signal else 0,
        "automatic": case.profile.get("workflow") == "fictional-two-decisions-v1",
        "plans": len(top),
        "rated": len(ratings),
        "edited": sum(r.is_edited for r in ratings.values()),
        "coverage": {k: v.get("level") for k, v in needs.get("coverage", {}).items()},
        "must_have": [k for k, v in needs.get("coverage", {}).items() if v.get("must_have")],
        "underwriting": needs.get("preferred_underwriting"),
        "state_durations": dict(by_state),
        "state_entered_at": entered,
        "selected_count": len(chosen),
        "accepted": saved.get("consumer_response", {}).get("decision") == "ACCEPTED",
        "bound": bool(saved.get("policy_bound")),
        "consumer_key": hashlib.sha256(case.profile["consumer_reference"].encode()).hexdigest()
        if case.profile.get("consumer_reference")
        else None,
        "renewal_of": case.profile.get("renewal_of_case_id"),
        "halt_code": next(
            (
                e.type
                for e in reversed(events)
                if e.payload.get("to") in {"PAUSED_NEEDS_HUMAN", "UW_REFERRAL", "COMPLAINT_FLAGGED"}
            ),
            None,
        ),
    }
    # Source prose and health declarations never enter the operational projection.
    db.execute(delete(ProviderMetric).where(ProviderMetric.case_id == case.id))
    groups = defaultdict(list)
    for plan in plans.values():
        if plan.get("insurerId"):
            groups[plan["insurerId"]].append(plan)
    accepted = saved.get("consumer_response", {}).get("selected_plan_id")
    for insurer, policies in groups.items():
        durations = [p["turnaroundDays"] for p in policies if p.get("turnaroundDays") is not None]
        upheld = [
            p["insurerStats"]["upheldRate"]
            for p in policies
            if p.get("insurerStats", {}).get("upheldRate") is not None
        ]
        db.add(
            ProviderMetric(
                case_id=case.id,
                insurer_id=insurer,
                broker_id=case.assigned_to,
                coverage_type=metric.coverage_type,
                created_at=case.created_at,
                shown=len(policies),
                top_three=sum(r.get("plan", {}).get("insurerId") == insurer for r in top[:3]),
                selected=sum(p.get("id") in chosen for p in policies),
                accepted=int(any(p.get("id") == accepted for p in policies)),
                rated_highly=sum(ratings[p["id"]].stars >= 4 for p in policies if p.get("id") in ratings),
                quoted_turnaround=sum(durations) / len(durations) if durations else None,
                upheld_rate=sum(upheld) / len(upheld) if upheld else None,
            )
        )
    return metric


def project_events(db, events):
    case_ids = set(db.info.pop("metrics_dirty", set())) | {e["case_id"] for e in events}
    if not case_ids:
        return
    db.flush()
    cases = {case.id: case for case in db.scalars(select(Case).where(Case.id.in_(case_ids)))}
    for case in cases.values():
        project_case(db, case)
    if cases:
        db.info["metrics_cache_invalidate"] = True
    for event in events:
        case = cases.get(event["case_id"])
        if not case:
            continue
        target = event["payload"].get("to")
        kind = (
            "case.created"
            if event["seq"] == 1
            else "case.halted"
            if target in {"PAUSED_NEEDS_HUMAN", "UW_REFERRAL", "COMPLAINT_FLAGGED"}
            else "rating.unblocked"
            if target == "BROKER_REVIEW"
            else "case.updated"
        )
        if not target and event["seq"] != 1:
            continue
        users = db.scalars(
            select(User).where(User.is_active.is_(True), User.id == case.assigned_to)
            if case.assigned_to
            else select(User).where(User.is_active.is_(True), User.role == "authorised_broker")
        ).all()
        for user in users:
            key = f"activity:{event['case_id']}:{event['seq']}"
            if db.scalar(
                select(Notification.id).where(
                    Notification.broker_id == user.id, Notification.event_key == key
                )
            ):
                continue
            title = {
                "case.created": "New case",
                "case.halted": "Case needs attention",
                "rating.unblocked": "Policies ready for your review",
                "case.updated": "Case progressed",
            }[kind]
            notification = Notification(
                broker_id=user.id,
                case_id=case.id,
                event_key=key,
                event_type=kind,
                body={
                    "title": title,
                    "message": case.profile.get("name", "Saved case"),
                    "state": case.state,
                    "href": f"/case/{case.id}",
                },
                actionable=kind != "case.updated",
            )
            db.add(notification)
            db.flush()
            if db.bind.dialect.name == "postgresql":
                db.execute(
                    text("SELECT pg_notify('broker_events', :payload)"),
                    {
                        "payload": json.dumps(
                            {"broker_id": user.id, "notification_id": notification.id, "case_id": case.id}
                        )
                    },
                )
