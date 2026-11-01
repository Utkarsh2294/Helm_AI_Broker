"""Scheduled SLA warnings, timezone digests and projection refresh."""

from datetime import datetime
import json
from zoneinfo import ZoneInfo
from sqlalchemy import select, text
from app.db.models import User, utcnow
from app.db.copilot import Notification, CaseMetric, CopilotPreferences
from app.copilot_projection import SLA_DAYS


def maintenance(db):
    now = utcnow()
    metrics = db.scalars(select(CaseMetric).where(CaseMetric.state.notin_(["PUBLISHED", "CLOSED"]))).all()
    users = db.scalars(select(User).where(User.is_active.is_(True), User.role == "authorised_broker")).all()
    for user in users:
        owned = [m for m in metrics if m.broker_id in (user.id, None)]
        preference = db.get(CopilotPreferences, user.id)
        if not preference:
            preference = CopilotPreferences(broker_id=user.id, timezone="Europe/London", voice_banner=False)
            db.add(preference)
        local = now.astimezone(ZoneInfo(preference.timezone))
        digest = local.hour >= 8 and preference.digest_day != local.date().isoformat()

        def add(key, kind, title, case_id=None):
            if not db.scalar(
                select(Notification.id).where(
                    Notification.broker_id == user.id, Notification.event_key == key
                )
            ):
                db.add(
                    Notification(
                        broker_id=user.id,
                        case_id=case_id,
                        event_key=key,
                        event_type=kind,
                        body={
                            "title": title,
                            "message": "Open the priority queue to review saved case records.",
                            "href": f"/case/{case_id}?view=audit" if case_id else "/queue?sort=priority",
                        },
                    )
                )
                db.flush()
                if db.bind.dialect.name == "postgresql":
                    db.execute(
                        text("SELECT pg_notify('broker_events',:payload)"),
                        {
                            "payload": json.dumps(
                                {"broker_id": user.id, "case_id": case_id, "event_type": kind}
                            )
                        },
                    )

        if digest:
            add(
                "digest:" + local.date().isoformat(),
                "case.pending_today",
                f"{len(owned)} cases pending today",
            )
            preference.digest_day = local.date().isoformat()
        for metric in owned:
            fraction = (
                max(0, (now - datetime.fromisoformat(metric.last_action_at)).total_seconds())
                / 86400
                / SLA_DAYS.get(metric.coverage_type, 5)
            )
            if fraction >= 0.8:
                add(
                    f"sla:{metric.case_id}:{now.date()}",
                    "case.sla_warning",
                    "Case approaching its demo SLA" if fraction < 1 else "Case is past its demo SLA",
                    metric.case_id,
                )


def refresh_daily_view(db):
    if db.bind.dialect.name == "postgresql":
        db.execute(text("REFRESH MATERIALIZED VIEW mv_case_daily_stats"))
    db.info["metrics_cache_invalidate"] = True


def preview_operational(session_factory, refresh=False, drivers=False):
    """Same scheduled work for the single-process local preview without Arq."""
    with session_factory() as db:
        maintenance(db)
        if refresh:
            refresh_daily_view(db)
        if drivers:
            from app.broker_insights import compute_drivers

            compute_drivers(db)
            detect_aging(db)
        db.commit()


def detect_aging(db):
    from datetime import timedelta
    from app.broker_insights import anomaly_report, build_context

    for user in db.scalars(
        select(User).where(
            User.is_active.is_(True), User.role.in_(["authorised_broker", "senior_broker", "lead_broker"])
        )
    ):
        ctx = build_context(db, user, utcnow().date() - timedelta(days=365), utcnow().date())
        signals = anomaly_report(ctx, limit=None)
        flagged = {item["case_id"]: item for item in signals["items"]}
        for metric in db.scalars(
            select(CaseMetric).where(
                CaseMetric.broker_id == user.id, CaseMetric.state.not_in(["PUBLISHED", "CLOSED"])
            )
        ):
            signal = flagged.get(metric.case_id)
            metric.body = {**metric.body, "aging_signal": signal, "priority_boost": 25 if signal else 0}
            metric.updated_at = utcnow().isoformat()
    db.info["metrics_cache_invalidate"] = True
