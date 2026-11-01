"""Arq wakes persisted jobs; restarting the worker never loses quotation deadlines."""

from datetime import timezone
from zoneinfo import ZoneInfo
from arq import cron
from arq.connections import RedisSettings
from app.config import settings
from sqlalchemy import select
from app.db.models import ModelProposal, utcnow
from app.db.store import SessionLocal
from app.service import learning_run, process_due_jobs
from app.audit_jobs import nightly_verify
import asyncio


async def poll_jobs(ctx):
    await asyncio.to_thread(run_due_jobs)


def run_due_jobs():
    from opentelemetry import trace

    with trace.get_tracer("helm.jobs").start_as_current_span("jobs.poll", record_exception=False):
        _run_due_jobs()


def _run_due_jobs():
    with SessionLocal() as db:
        process_due_jobs(db)
        db.commit()


async def daily_learning(ctx):
    london = utcnow().astimezone(ZoneInfo("Europe/London"))
    if london.hour < 2:
        return
    midnight = london.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).isoformat()
    with SessionLocal() as db:
        # One proposal per London day, even after worker restart or a repeated cron invocation.
        previous = db.scalar(select(ModelProposal).where(ModelProposal.created_at >= midnight).limit(1))
        if not previous:
            learning_run(db)
            db.commit()


async def copilot_maintenance(ctx):
    def run():
        from app.copilot_jobs import maintenance

        with SessionLocal() as db:
            maintenance(db)
            db.commit()

    await asyncio.to_thread(run)


async def refresh_insights(ctx):
    def run():
        from app.copilot_jobs import refresh_daily_view

        with SessionLocal() as db:
            refresh_daily_view(db)
            db.commit()

    await asyncio.to_thread(run)


async def browser_push(ctx):
    def run():
        from app.push_notifications import deliver_pending

        with SessionLocal() as db:
            deliver_pending(db)
            db.commit()

    await asyncio.to_thread(run)


async def satisfaction_drivers(ctx):
    def run():
        from app.broker_insights import compute_drivers
        from app.copilot_jobs import detect_aging

        with SessionLocal() as db:
            compute_drivers(db)
            detect_aging(db)
            db.commit()

    await asyncio.to_thread(run)


class WorkerSettings:
    @staticmethod
    async def on_startup(ctx):
        from app.observability import configure
        from app.agents.runtime import prepare_runtime

        configure()
        await asyncio.to_thread(prepare_runtime, settings().agent_runtime)
        await refresh_insights(ctx)

    redis_settings = RedisSettings.from_dsn(settings().redis_url)
    functions = [
        poll_jobs,
        daily_learning,
        nightly_verify,
        copilot_maintenance,
        refresh_insights,
        browser_push,
        satisfaction_drivers,
    ]
    cron_jobs = [
        cron(poll_jobs, second=set(range(60))),
        cron(daily_learning, minute=0),
        cron(nightly_verify, hour=3, minute=0),
        cron(copilot_maintenance, minute=set(range(60))),
        cron(refresh_insights, minute={0, 15, 30, 45}),
        cron(browser_push, second={0, 10, 20, 30, 40, 50}),
        cron(satisfaction_drivers, hour=2, minute=30),
    ]
    max_jobs = 2
