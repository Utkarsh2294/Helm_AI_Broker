"""Broker task guidance and replayable, session-checked notification streams."""

import asyncio
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import Field
from sqlalchemy import select, func, or_, and_, update, delete
from sqlalchemy.exc import IntegrityError
from app import service
from app.auth import identity
from app.cursors import encode_cursor, decode_cursor, filter_hash
from app.db.models import Case, uid, utcnow
from app.db.copilot import CaseMetric, Notification, NotificationLease, TaskSnooze, CopilotPreferences
from app.demo_documents import database
from app.schemas import Model, DomainError
from app.copilot_projection import priority_score, SLA_DAYS
from app.db.async_session import OperationalRouter

router = OperationalRouter(prefix="/api/v1")
TASKS = {
    "FACTFIND_REVIEW": ("review_facts", "Review and sign off the fact-find", "journey"),
    "AWAIT_BROKER_RELEASE": ("release_quotes", "Review the panel and release quotations", "journey"),
    "BROKER_REVIEW": ("rate_plans", "Review and rate the shortlisted plans", "journey"),
    "AWAIT_APPROVAL": ("final_signoff", "Review and give final sign-off", "journey"),
    "PAUSED_NEEDS_HUMAN": ("resolve_halt", "Review the recorded hold", "audit"),
    "COMPLAINT_FLAGGED": ("resolve_complaint", "Review the complaint with its owner", "journey"),
    "UW_REFERRAL": ("resolve_referral", "Review the underwriter referral", "journey"),
    "NEEDS_INFO": ("missing_information", "Review the missing information", "file"),
}


def senior(user):
    return user.role in {"senior_broker", "admin"} or user.is_lead_broker


def metric_scope(user, broker_id=None, model=CaseMetric):
    if broker_id and broker_id != user.id:
        if not senior(user):
            raise DomainError(
                "Senior broker or administrator access is required for another broker's metrics", 403
            )
        return True if broker_id == "all" else model.broker_id == broker_id
    return or_(model.broker_id == user.id, model.broker_id.is_(None))


def notification_scope(user):
    return and_(
        Notification.broker_id == user.id,
        or_(
            Notification.case_id.is_(None),
            Notification.case_id.in_(
                select(Case.id).where(or_(Case.assigned_to == user.id, Case.assigned_to.is_(None)))
            ),
        ),
    )


def notification_data(row):
    return {
        "id": row.id,
        "case_id": row.case_id,
        "event_type": row.event_type,
        "created_at": row.created_at,
        "read_at": row.read_at,
        "actionable": row.actionable,
        **row.body,
    }


def task_cards(db, user, broker_id=None, include_snoozed=False, case_id=None):
    now = utcnow()
    rows = db.scalars(
        select(CaseMetric).where(
            metric_scope(user, broker_id),
            CaseMetric.state.in_(TASKS),
            CaseMetric.case_id == case_id if case_id else True,
        )
    ).all()
    snoozes = {
        (r.case_id, r.task_key): r
        for r in db.scalars(
            select(TaskSnooze).where(
                TaskSnooze.broker_id == user.id, TaskSnooze.snoozed_until > now.isoformat()
            )
        )
    }
    result = []
    for metric in rows:
        automatic = metric.body.get("automatic")
        if automatic and metric.state in {"FACTFIND_REVIEW", "AWAIT_BROKER_RELEASE"}:
            continue
        key, title, view = TASKS[metric.state]
        if automatic and metric.state == "BROKER_REVIEW":
            key, title = "select_policies", "Choose and rank three policies"
        if not include_snoozed and (metric.case_id, key) in snoozes:
            continue
        total, rated = metric.body.get("plans", 0), metric.body.get("rated", 0)
        source = {
            "state": metric.state,
            "last_action_at": metric.last_action_at,
            "coverage_type": metric.coverage_type,
            "unrated_plan_fraction": (total - rated) / total if total else 1,
        }
        days = max(0, (now - datetime.fromisoformat(metric.last_action_at)).days)
        score = priority_score(source, now)
        result.append(
            {
                "case_id": metric.case_id,
                "task_key": key,
                "type": key,
                "title": title,
                "client": "Saved case",
                "state": metric.state,
                "priority_score": score + metric.body.get("priority_boost", 0),
                "base_priority_score": score,
                "aging_signal": metric.body.get("aging_signal"),
                "overdue": days >= SLA_DAYS.get(metric.coverage_type, 5),
                "elapsed_days": days,
                "sla_days": SLA_DAYS.get(metric.coverage_type, 5),
                "rated": rated,
                "total": total,
                "halt_code": metric.body.get("halt_code"),
                "last_action_at": metric.last_action_at,
                "href": f"/case/{metric.case_id}?view={view}",
                "estimated_minutes": None,
                "estimate_notice": "No reliable historical task timing is recorded yet.",
                "source": f"case_metrics:{metric.case_id}:{metric.updated_at}",
                "snoozed_until": snoozes.get((metric.case_id, key)).snoozed_until
                if (metric.case_id, key) in snoozes
                else None,
            }
        )
    from app.buying_tasks import task_cards as buying_cards

    result.extend(buying_cards(db, user, broker_id, include_snoozed, case_id))
    return sorted(result, key=lambda t: (-t["priority_score"], t["last_action_at"], t["case_id"]))


@router.get("/tasks/rail")
def rail(
    request: Request,
    broker_id: str | None = None,
    case_id: str | None = None,
    db=Depends(database, scope="function"),
):
    user, _ = identity(db, request)
    if case_id:
        service.get_case(db, case_id)
    cards = task_cards(db, user, broker_id, case_id=case_id)
    names = (
        {
            case.id: case.profile.get("name", "Saved case")
            for case in db.scalars(select(Case).where(Case.id.in_([task["case_id"] for task in cards[:50]])))
        }
        if cards
        else {}
    )
    return {
        "items": [{**task, "client": names.get(task["case_id"], "Saved case")} for task in cards[:50]],
        "total": len(cards),
        "priority_basis": "Configured demo SLA: five calendar days since the last recorded broker action; state and review progress. No model sets priorities.",
        "generated_at": utcnow().isoformat(),
    }


class SnoozeInput(Model):
    reason: str = Field(default="later", pattern="^(later|waiting_on_consumer|waiting_on_insurer_docs)$")


@router.post("/tasks/{case_id}/{task_key}/snooze")
def snooze(
    case_id: str, task_key: str, body: SnoozeInput, request: Request, db=Depends(database, scope="function")
):
    user, _ = identity(db, request)
    service.get_case(db, case_id)
    task = next(
        (
            t
            for t in task_cards(db, user, include_snoozed=True)
            if t["case_id"] == case_id and t["task_key"] == task_key
        ),
        None,
    )
    if not task:
        raise DomainError("This task is no longer outstanding in your queue", 409)
    row = db.get(TaskSnooze, (user.id, case_id, task_key))
    if not row:
        row = TaskSnooze(broker_id=user.id, case_id=case_id, task_key=task_key)
        db.add(row)
    row.snoozed_until, row.reason = (utcnow() + timedelta(hours=1)).isoformat(), body.reason
    return {"snoozed_until": row.snoozed_until, "reason": row.reason}


@router.get("/dashboard/priority-summary")
def priority_summary(request: Request, db=Depends(database, scope="function")):
    user, _ = identity(db, request)
    items = task_cards(db, user, include_snoozed=True)
    preference = db.get(CopilotPreferences, user.id)
    since = (
        preference.previous_login if preference and preference.previous_login else utcnow().date().isoformat()
    )
    new = db.scalar(
        select(func.count()).select_from(CaseMetric).where(metric_scope(user), CaseMetric.created_at > since)
    )
    return {
        "action_needed": len(items),
        "overdue": sum(t["overdue"] for t in items),
        "halted": sum(
            t["state"] in {"PAUSED_NEEDS_HUMAN", "COMPLAINT_FLAGGED", "UW_REFERRAL"} for t in items
        ),
        "new": new,
        "href": "/queue?sort=priority",
        "login_epoch": preference.last_login if preference else since,
        "voice_banner": bool(preference and preference.voice_banner),
    }


@router.get("/notifications")
def inbox(
    request: Request,
    cursor: str = "",
    actionable: bool = False,
    limit: int = Query(20, ge=1, le=100),
    db=Depends(database, scope="function"),
):
    user, _ = identity(db, request)
    scope = notification_scope(user)
    query = select(Notification).where(scope)
    if actionable:
        query = query.where(Notification.actionable.is_(True))
    binding = filter_hash([user.id, "notifications", actionable])
    if cursor:
        stamp, identifier, _ = decode_cursor(cursor, binding)
        query = query.where(
            or_(
                Notification.created_at < stamp,
                and_(Notification.created_at == stamp, Notification.id < identifier),
            )
        )
    rows = db.scalars(
        query.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit + 1)
    ).all()
    more, rows = len(rows) > limit, rows[:limit]
    return {
        "items": [notification_data(row) for row in rows],
        "unread": db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(scope, Notification.read_at.is_(None), Notification.actionable.is_(True))
        ),
        "next_cursor": encode_cursor([rows[-1].created_at, rows[-1].id, ""], binding) if more else None,
    }


@router.post("/notifications/read-all")
def read_all(request: Request, db=Depends(database, scope="function")):
    user, _ = identity(db, request)
    db.execute(
        update(Notification)
        .where(notification_scope(user), Notification.read_at.is_(None))
        .values(read_at=utcnow().isoformat())
    )
    return {"read": True}


@router.post("/notifications/{notification_id}/read")
def read_one(notification_id: str, request: Request, db=Depends(database, scope="function")):
    user, _ = identity(db, request)
    row = db.scalar(select(Notification).where(notification_scope(user), Notification.id == notification_id))
    if not row:
        raise DomainError("Notification not found", 404)
    row.read_at = row.read_at or utcnow().isoformat()
    return {"read": True}


def claim_stream(db, user):
    token, now = uid(), utcnow()
    row = db.scalar(select(NotificationLease).where(NotificationLease.broker_id == user.id).with_for_update())
    if row and row.expires_at > now.isoformat():
        raise DomainError(
            "A live notification stream is already open for this broker. Close the other tab or refresh the inbox.",
            409,
        )
    try:
        with db.begin_nested():
            if not row:
                row = NotificationLease(broker_id=user.id)
                db.add(row)
            row.token, row.expires_at = token, (now + timedelta(seconds=40)).isoformat()
            db.flush()
    except IntegrityError:
        raise DomainError("A live notification stream is already open for this broker", 409)
    return token


@router.get("/notifications/stream")
def stream(request: Request, cursor: str = "", db=Depends(database, scope="function")):
    user, _ = identity(db, request)
    token = claim_stream(db, user)
    binding = filter_hash([user.id, "notification_stream"])
    position = (
        decode_cursor(request.headers.get("Last-Event-ID") or cursor, binding)
        if request.headers.get("Last-Event-ID") or cursor
        else [utcnow().isoformat(), "", ""]
    )
    broker_id = user.id

    def fetch_rows(position):
        from app.main import SessionLocal

        with SessionLocal() as connection:
            current, _ = identity(connection, request)
            lease = connection.get(NotificationLease, broker_id)
            if not lease or lease.token != token:
                return None
            lease.expires_at = (utcnow() + timedelta(seconds=40)).isoformat()
            rows = connection.scalars(
                select(Notification)
                .where(
                    notification_scope(current),
                    or_(
                        Notification.created_at > position[0],
                        and_(Notification.created_at == position[0], Notification.id > position[1]),
                    ),
                )
                .order_by(Notification.created_at, Notification.id)
                .limit(100)
            ).all()
            payload = [notification_data(row) for row in rows]
            connection.commit()
            return payload

    def release():
        from app.main import SessionLocal

        with SessionLocal() as connection:
            connection.execute(
                delete(NotificationLease).where(
                    NotificationLease.broker_id == broker_id, NotificationLease.token == token
                )
            )
            connection.commit()

    async def events():
        nonlocal position
        listener = None
        try:
            from app.config import settings

            if settings().database_url.startswith("postgresql"):

                def listen():
                    import psycopg

                    connection = psycopg.connect(
                        settings().database_url.replace("postgresql+psycopg:", "postgresql:"), autocommit=True
                    )
                    connection.execute("LISTEN broker_events")
                    return connection

                listener = await asyncio.to_thread(listen)
            # Durable replay is authoritative; PostgreSQL NOTIFY is a wake-up signal,
            # never the only copy of an event. Session/assignment checks repeat each poll.
            for _ in range(25):
                if await request.is_disconnected():
                    break
                try:
                    rows = await asyncio.to_thread(fetch_rows, position)
                except DomainError:
                    break
                if rows is None:
                    break
                for row in rows:
                    position = [row["created_at"], row["id"], ""]
                    yield f"id: {encode_cursor(position, binding)}\ndata: {json.dumps(row)}\n\n"
                yield ": heartbeat\n\n"
                if listener:
                    await asyncio.to_thread(lambda: next(listener.notifies(timeout=1, stop_after=1), None))
                else:
                    await asyncio.sleep(1)
        finally:
            if listener:
                await asyncio.to_thread(listener.close)
            await asyncio.to_thread(release)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


class PreferenceInput(Model):
    timezone: str = Field(default="Europe/London", max_length=80)
    voice_banner: bool = False


@router.put("/notifications/preferences")
def preferences(body: PreferenceInput, request: Request, db=Depends(database, scope="function")):
    user, _ = identity(db, request)
    try:
        ZoneInfo(body.timezone)
    except ZoneInfoNotFoundError:
        raise DomainError("Choose a valid IANA timezone", 422)
    row = db.get(CopilotPreferences, user.id)
    if not row:
        row = CopilotPreferences(broker_id=user.id)
        db.add(row)
    row.timezone, row.voice_banner = body.timezone, body.voice_banner
    return {"timezone": row.timezone, "voice_banner": row.voice_banner}


@router.get("/notifications/preferences")
def read_preferences(request: Request, db=Depends(database, scope="function")):
    user, _ = identity(db, request)
    row = db.get(CopilotPreferences, user.id)
    return {
        "timezone": row.timezone if row else "Europe/London",
        "voice_banner": row.voice_banner if row else False,
    }


class ExplainInput(Model):
    case_id: str = Field(min_length=1, max_length=100)
    task_key: str = Field(default="", max_length=60)


@router.post("/assistant/explain-task")
def explain_task(body: ExplainInput, request: Request, db=Depends(database, scope="function")):
    from app.assistant import record_answer
    from app.case_workspace import Question

    user, session = identity(db, request)
    service.get_case(db, body.case_id)
    task = next(
        (
            t
            for t in task_cards(db, user, include_snoozed=True)
            if t["case_id"] == body.case_id and (not body.task_key or t["task_key"] == body.task_key)
        ),
        None,
    )
    if not task:
        raise DomainError("No outstanding broker task is recorded for this case", 409)
    result = {
        "answer": f"Your role is to {task['title'].lower()}. [1]\nReview the saved client requirements, coverage gaps and source documents before recording your judgement. Keep policy selection and authenticated final sign-off as your own decisions. [1]\nCheck any missing or uncertain information in the digital file and audit before continuing. A snooze only hides the task for one hour; it does not resolve the case. [1]",
        "sources": [
            {
                "label": "Current case task and saved workflow state",
                "record": task["source"],
                "case_id": body.case_id,
                "view": "journey",
            }
        ],
        "confidence": "HIGH",
        "suggestions": [
            "What should I do next?",
            "What are the client’s preferences?",
            "What did each agent do?",
        ],
        "actions_performed": [],
        "compliance_context": ["ICOBS 5/6: review against your firm's approved rule text"],
        "mode": "local_saved_evidence",
        "protected": False,
    }
    return record_answer(
        db,
        user,
        session,
        Question(case_id=body.case_id, question="Why this task matters: " + task["task_key"]),
        result,
    )
