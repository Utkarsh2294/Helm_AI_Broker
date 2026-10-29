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


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings().redis_url)
    functions = [poll_jobs, daily_learning, nightly_verify]
    cron_jobs = [
        cron(poll_jobs, second={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
        cron(daily_learning, minute=0),
        cron(nightly_verify, hour=3, minute=0),
    ]
    max_jobs = 1
