"""Infrastructure routes shared by the prototype phases."""

import json
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from redis import Redis
from sqlalchemy import select, text
from app.config import settings
from app.core_client.client import verify_signature
from app.db.models import Case
from app.db.platform import InboxEvent
from app.db.store import audit
from app.main import database
from app.schemas import DomainError, QuoteRequest
from app.schemas import Model
from pydantic import Field
from app.auth import identity
from app.db.store import latest
from app import service

router = APIRouter(prefix="/api/v1")


class CopilotQuestion(Model):
    question: str = Field(min_length=1, max_length=500)
    ranking_id: str


@router.post("/cases/{case_id}/ranking/copilot")
def copilot(case_id: str, body: CopilotQuestion, request: Request, db=Depends(database, scope="function")):
    identity(db, request)
    service.get_case(db, case_id)
    ranking = latest(db, case_id, "ranking")
    if not ranking or ranking.body["id"] != body.ranking_id:
        raise DomainError("Ranking changed; refresh before asking")
    from app.copilot import answer_question

    return answer_question(ranking.body, body.question)


@router.get("/health")
def readiness(db=Depends(database, scope="function")):
    checks = {"db": "error", "redis": "error"}
    try:
        db.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception:
        db.rollback()
    try:
        with Redis.from_url(settings().redis_url, socket_connect_timeout=1, socket_timeout=1) as redis:
            checks["redis"] = "ok" if redis.ping() else "error"
    except Exception:
        pass
    ok = all(value == "ok" for value in checks.values())
    return JSONResponse(
        {
            "status": "ok" if ok else "degraded",
            "db_backend": settings().database_url.split(":", 1)[0],
            **checks,
        },
        status_code=200 if ok else 503,
    )


@router.post("/webhooks/core")
async def receive_webhook(request: Request, db=Depends(database, scope="function")):
    raw = await request.body()
    if len(raw) > 1_000_000:
        raise DomainError("Webhook too large", 413)
    verify_signature(
        raw, request.headers.get("X-Helm-Timestamp", ""), request.headers.get("X-Helm-Signature", "")
    )
    try:
        event = json.loads(raw)
        event_id, event_type = str(event["id"]), str(event["type"])
        if len(event_id) > 100:
            raise ValueError("id too long")
    except (ValueError, KeyError, TypeError):
        raise DomainError("Invalid event envelope", 422)
    if db.get(InboxEvent, event_id):
        return {"received": True, "duplicate": True}
    if event_type in ('quote_request.submitted', 'case.created'):
        case = service.import_request(db, QuoteRequest.model_validate(event.get('request')))
    elif event_type.startswith("recommendation."):
        case = db.scalar(select(Case).where(Case.id == event.get("case_id")))
        if not case:
            raise DomainError("Case not found", 404)
        audit(db, case.id, event_type, "consumer", {"outcome": event_type.rsplit(".", 1)[-1]})
    else:
        raise DomainError("Unsupported webhook event", 422)
    db.add(InboxEvent(id=event_id, event_type=event_type, body=event))
    return {"received": True, "case_id": case.id}
