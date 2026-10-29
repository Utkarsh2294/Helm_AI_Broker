import asyncio
import json
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from app.auth import authenticate, identity, new_session, public_user, verify_password
from app.agents.review import canonical_hash
from app.agents.quotation import PARTNERS, Scenario
from app.agents.runtime import AGENTS
from app.config import settings
from app.db.models import Activity, Case, ModelProposal, utcnow
from app.db.store import SessionLocal, latest, save_snapshot, audit
from app.demo import seed_demo
from app.schemas import DNR, DomainError, Fact, Model, QuoteRequest, State, Survey
from app import service


def database():
    with SessionLocal() as db:
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise


@asynccontextmanager
async def lifespan(app):
    with SessionLocal() as db:
        seed_demo(db)
    yield


app = FastAPI(title="Helm Broker API", version="0.1.0", lifespan=lifespan,
              description="Demo-first five-agent workspace. No real insurer delivery.")


@app.middleware("http")
async def request_boundary(request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        # Browser requests require the configured same-origin proxy. CLI/worker requests use cookies+CSRF.
        if origin and origin != settings().allowed_origin:
            return JSONResponse({"detail": "Unapproved request origin"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(DomainError)
async def domain_error(request, error):
    return JSONResponse({"type": "about:blank", "title": str(error), "detail": str(error),
                         "status": error.status}, status_code=error.status, media_type="application/problem+json")


@app.exception_handler(StaleDataError)
@app.exception_handler(IntegrityError)
async def conflict(request, error):
    return JSONResponse({"detail": "Data changed concurrently; refresh and retry"}, status_code=409)


class Credentials(Model):
    email: str = Field(default="broker@helm.demo", max_length=200)
    password: str = Field(min_length=1, max_length=256)


class StepUp(Model):
    password: str = Field(min_length=1, max_length=256)


class Action(Model):
    scenario: Scenario = "happy"
    medical_released: bool = False
    ranking_id: str = ""
    selected: list[str] = Field(default_factory=list, max_length=3)
    survey: Survey | None = None
    acknowledgements: list[str] = Field(default_factory=list)
    suitability: str | None = Field(default=None, max_length=20000)
    pack_hash: str = ""


class EditDNR(Model):
    dnr: DNR
    reason: str = Field(min_length=3, max_length=500)


class SuitabilityEdit(Model):
    text: str = Field(min_length=20, max_length=20000)


# shortcut: per-process login throttle for a local demo; replace with shared Redis limits before live use.
attempts = {}


@app.get("/health")
def health():
    return {"status": "ok", "mode": settings().mode, "agent_runtime": settings().agent_runtime}


@app.post("/api/v1/auth/password")
def login(body: Credentials, request: Request, response: Response, db=Depends(database)):
    address = request.client.host if request.client else "local"
    now = utcnow().timestamp()
    attempts[address] = [t for t in attempts.get(address, []) if t > now - 60]
    if len(attempts[address]) >= 10:
        raise DomainError("Too many attempts; try again in a minute", 429)
    attempts[address].append(now)
    user = authenticate(db, body.email, body.password)
    session, token = new_session(db, user)
    response.set_cookie("helm_session", token, httponly=True, secure=settings().cookie_secure,
                        samesite="strict", max_age=settings().session_hours * 3600, path="/")
    return {"user": public_user(user), "csrf": session.csrf}


@app.get("/api/v1/auth/session")
def session(request: Request, db=Depends(database)):
    user, session = identity(db, request)
    return {"user": public_user(user), "csrf": session.csrf}


@app.post("/api/v1/auth/logout")
def logout(request: Request, response: Response, db=Depends(database)):
    _, session = identity(db, request)
    db.delete(session)
    response.delete_cookie("helm_session", path="/")
    return {"ok": True}


@app.post("/api/v1/auth/step-up")
def step_up(body: StepUp, request: Request, db=Depends(database)):
    user, session = identity(db, request)
    if not verify_password(body.password, user.password_hash):
        raise DomainError("Password is incorrect", 401)
    session.step_up_at = utcnow().isoformat()
    return {"ok": True, "expires_in": 300}


@app.get("/api/v1/agents")
def agents(request: Request, db=Depends(database)):
    identity(db, request)
    return {"agents": AGENTS, "runtime": settings().agent_runtime, "llm_enabled": False}


@app.get("/api/v1/partners")
def partners(request: Request, db=Depends(database)):
    identity(db, request)
    return PARTNERS


@app.get("/api/v1/cases")
def cases(request: Request, q: str = "", state: str = "", db=Depends(database)):
    identity(db, request)
    service.process_due_jobs(db)
    rows = db.scalars(select(Case).order_by(Case.created_at.desc())).all()
    return [{"id": c.id, **c.profile, "state": c.state, "created_at": c.created_at,
             "assigned_to": c.assigned_to, "version": c.version}
            for c in rows if (not q or q.lower() in c.profile["name"].lower()) and (not state or c.state == state)]


@app.post("/api/v1/demo/requests")
def create_demo_request(body: QuoteRequest, request: Request, db=Depends(database)):
    user, _ = identity(db, request)
    service.require_broker(user)
    return service.detail(db, service.import_request(db, body))


@app.get("/api/v1/cases/{case_id}")
def case_detail(case_id: str, request: Request, db=Depends(database)):
    identity(db, request)
    service.process_due_jobs(db)
    return service.detail(db, service.get_case(db, case_id))


@app.patch("/api/v1/cases/{case_id}/dnr")
def edit_dnr(case_id: str, body: EditDNR, request: Request, db=Depends(database)):
    user, _ = identity(db, request)
    service.require_broker(user)
    case = service.get_case(db, case_id)
    if case.state not in (State.NEEDS_INFO, State.FACTFIND_REVIEW, State.AWAIT_BROKER_RELEASE):
        raise DomainError("Return the case to fact-find review before changing requirements")
    previous = latest(db, case_id, "dnr")
    if body.dnr.request_id != previous.body["request_id"]:
        raise DomainError("Request identity cannot be changed", 422)
    revised = body.dnr.model_copy(update={"version": previous.version + 1})
    if revised.needs.budget_annual_pence != previous.body["needs"]["budget_annual_pence"]:
        revised.facts["budget_annual_pence"] = Fact(value=revised.needs.budget_annual_pence,
            source=f"broker_edit:{case_id}:v{revised.version}", verified_by=user.id)
    save_snapshot(db, case_id, "dnr", revised.model_dump())
    save_snapshot(db, case_id, "dnr_edit", {"reason": body.reason, "by": user.id, "version": revised.version})
    service.transition(db, case, [case.state], State.NEEDS_INFO if revised.missing else State.FACTFIND_REVIEW,
                       "dnr_revised", f"broker:{user.id}", {"version": revised.version})
    return service.detail(db, case)


@app.post("/api/v1/cases/{case_id}/{action}")
def case_action(case_id: str, action: Literal["sign-off", "release", "selection", "approve", "pause", "resume",
                                             "assign", "request-changes", "complaint", "resolve"],
                body: Action, request: Request, db=Depends(database)):
    user, session = identity(db, request)
    if action == "selection" and body.survey is None:
        raise DomainError("Selection requires the short survey", 422)
    return service.act(db, case_id, action, user, session, body.model_dump())


@app.put("/api/v1/cases/{case_id}/suitability")
def edit_suitability(case_id: str, body: SuitabilityEdit, request: Request, db=Depends(database)):
    user, _ = identity(db, request)
    service.require_broker(user)
    case = service.get_case(db, case_id)
    if case.state != State.AWAIT_APPROVAL:
        raise DomainError("Only a draft awaiting approval can be edited")
    previous = latest(db, case_id, "pack").body
    revised = {k: v for k, v in previous.items() if k != "pack_hash"}
    revised["suitability_final"] = body.text.strip()
    revised["pack_hash"] = canonical_hash(revised)
    save_snapshot(db, case_id, "pack", revised)
    audit(db, case_id, "suitability_edited", f"broker:{user.id}", {"pack_hash": revised["pack_hash"]})
    return service.detail(db, case)


@app.get("/api/v1/cases/{case_id}/evidence")
def export_evidence(case_id: str, request: Request, db=Depends(database)):
    user, _ = identity(db, request)
    case = service.get_case(db, case_id)
    result = service.evidence(db, case)
    audit(db, case_id, "evidence_exported", f"user:{user.id}")
    return result


@app.get("/api/v1/cases/{case_id}/stream")
async def stream(case_id: str, request: Request, after: int = 0, db=Depends(database)):
    identity(db, request)
    service.get_case(db, case_id)
    db.rollback()
    header = request.headers.get("Last-Event-ID", "0")
    cursor = max(after, int(header) if header.isdigit() else 0)

    async def events():
        nonlocal cursor
        # Finite streams force periodic session/expiry checks on browser reconnect.
        for _ in range(25):
            if await request.is_disconnected():
                break
            with SessionLocal() as connection:
                try:
                    identity(connection, request)
                except DomainError:
                    return
                rows = connection.scalars(select(Activity).where(Activity.case_id == case_id, Activity.seq > cursor)
                                           .order_by(Activity.seq)).all()
                for row in rows:
                    cursor = row.seq
                    data = {"type": row.type, "seq": row.seq, "payload": row.payload}
                    yield f"id: {row.seq}\ndata: {json.dumps(data)}\n\n"
            yield ": heartbeat\n\n"
            await asyncio.sleep(1)
    return StreamingResponse(events(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})


@app.get("/api/v1/models")
def models(request: Request, db=Depends(database)):
    identity(db, request)
    return [{"id": m.id, "created_at": m.created_at, **m.body}
            for m in db.scalars(select(ModelProposal).order_by(ModelProposal.created_at.desc())).all()]


@app.post("/api/v1/models/evaluate")
def evaluate(request: Request, db=Depends(database)):
    user, _ = identity(db, request)
    if user.role not in ("authorised_broker", "compliance_officer"):
        raise DomainError("Only advisers and compliance may run an evaluation", 403)
    return service.learning_run(db)
