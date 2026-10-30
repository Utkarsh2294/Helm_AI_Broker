"""SQL replay and Redis notifications; event payloads contain no medical statements."""

import asyncio
import json
import time
from types import SimpleNamespace
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from sqlalchemy import select
from app.auth import identity
from app.config import settings
from app.db.models import Activity
from app.db.store import SessionLocal
from app.main import database
from app.service import get_case

router = APIRouter(prefix="/api/v1/cases")


def event_dict(row):
    if isinstance(row, dict):
        row = SimpleNamespace(**row)
    return {
        "seq": row.seq,
        "case_id": row.case_id,
        "created_at": row.created_at,
        "ts": row.created_at,
        "actor": row.actor,
        "actor_type": row.actor.split(":")[0],
        "type": row.type,
        "payload": row.payload,
        "hash": row.hash,
        "ui_message": row.type.replace("_", " ").capitalize(),
    }


def fetch_events(case_id, cursor, request):
    with SessionLocal() as db:
        identity(db, request)
        get_case(db, case_id)
        return [
            event_dict(e)
            for e in db.scalars(
                select(Activity)
                .where(Activity.case_id == case_id, Activity.seq > cursor)
                .order_by(Activity.seq)
            )
        ]


@router.get("/{case_id}/events")
def events(case_id: str, request: Request, after: int = 0, db=Depends(database, scope="function")):
    identity(db, request)
    get_case(db, case_id)
    return [
        event_dict(e)
        for e in db.scalars(
            select(Activity).where(Activity.case_id == case_id, Activity.seq > after).order_by(Activity.seq)
        )
    ]


@router.get("/{case_id}/stream")
def stream(case_id: str, request: Request, after: int = 0, db=Depends(database, scope="function")):
    identity(db, request)
    get_case(db, case_id)
    db.rollback()
    header = request.headers.get("Last-Event-ID", "0")
    cursor = max(after, int(header) if header.isdigit() else 0)

    async def generate():
        nonlocal cursor
        client, pubsub = None, None
        started, last_check, last_heartbeat = time.monotonic(), 0, 0
        try:
            try:
                client = Redis.from_url(settings().redis_url, socket_connect_timeout=1)
                pubsub = client.pubsub()
                await pubsub.subscribe(f"case:{case_id}:events")
            except Exception:
                pubsub = None
            for event in await asyncio.to_thread(fetch_events, case_id, cursor, request):
                cursor = event["seq"]
                yield f"id: {cursor}\ndata: {json.dumps(event)}\n\n"
            last_check = time.monotonic()
            while time.monotonic() - started < 60 and not await request.is_disconnected():
                now = time.monotonic()
                message = (
                    await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1) if pubsub else None
                )
                gap = False
                if message:
                    try:
                        committed = json.loads(message["data"])
                        if committed["case_id"] != case_id:
                            continue
                        sequence = int(committed["seq"])
                        if sequence == cursor + 1:
                            event = event_dict(committed)
                            cursor = sequence
                            yield f"id: {cursor}\ndata: {json.dumps(event)}\n\n"
                        elif sequence > cursor:
                            gap = True
                    except (ValueError, TypeError, KeyError):
                        gap = True
                if gap or now - last_check > (5 if pubsub else 0.1):
                    last_check = now
                    try:
                        rows = await asyncio.to_thread(fetch_events, case_id, cursor, request)
                    except Exception:
                        return
                    for event in rows:
                        cursor = event["seq"]
                        yield f"id: {cursor}\ndata: {json.dumps(event)}\n\n"
                if now - last_heartbeat > 15:
                    last_heartbeat = now
                    yield ": keepalive\n\n"
                await asyncio.sleep(0.02 if pubsub else 0.1)
        finally:
            if pubsub:
                await pubsub.aclose()
            if client:
                await client.aclose()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
