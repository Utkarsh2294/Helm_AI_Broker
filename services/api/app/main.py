import asyncio
import json
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from app.auth import authenticate, identity, new_session, public_user, verify_password
from app.agents.review import canonical_hash
from app.agents.quotation import Scenario
from app.agents.runtime import AGENTS
from app.config import settings
from app.db.models import Activity, Case, ModelProposal, utcnow
from app.db.store import SessionLocal, latest, save_snapshot, audit
from app.demo import seed_demo
from app.schemas import DNR, DomainError, Fact, Model, QuoteRequest, State, Survey
from app import service
from app.compliance.medical_firewall import safe_case


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
    from app.agents.runtime import prepare_runtime
    from app.logging_setup import configure_logging
    from app.auth.tokens import signer

    configure_logging()
    signer()
    await asyncio.to_thread(prepare_runtime, settings().agent_runtime)
    with SessionLocal() as db:
        seed_demo(db)
    yield


app = FastAPI(
    title="Helm Broker API",
    version="0.1.0",
    lifespan=lifespan,
    description="Demo-first five-agent workspace. No real insurer delivery.",
)


@app.middleware("http")
async def request_boundary(request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        # Browser requests require the configured same-origin proxy. CLI/worker requests use cookies+CSRF.
        if origin and origin not in settings().trusted_origins:
            return JSONResponse({"detail": "Unapproved request origin"}, status_code=403)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        chunks, length = [], 0
        async for chunk in request.stream():
            length += len(chunk)
            if length > 2_000_000:
                return JSONResponse({"detail": "Request body too large"}, status_code=413)
            chunks.append(chunk)
        request._body = b"".join(chunks)
    response = await call_next(request)
    import structlog

    structlog.get_logger("helm.http").info(
        "http_request",
        method=request.method,
        route=getattr(request.scope.get("route"), "path", "unmatched"),
        status=response.status_code,
    )
    from app.security import CSP

    response.headers["Content-Security-Policy"] = CSP
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    if settings().cookie_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(DomainError)
async def domain_error(request, error):
    from app.security import denied_gate

    await asyncio.to_thread(denied_gate, SessionLocal, request, error.status)
    return JSONResponse(
        {
            "type": "about:blank",
            "title": str(error),
            "detail": str(error),
            "status": error.status,
            **error.flags,
        },
        status_code=error.status,
        media_type="application/problem+json",
    )


@app.exception_handler(StaleDataError)
@app.exception_handler(IntegrityError)
async def conflict(request, error):
    return JSONResponse({"detail": "Data changed concurrently; refresh and retry"}, status_code=409)


@app.exception_handler(ValidationError)
async def invalid_structured_data(request, error):
    return JSONResponse(
        {
            "detail": "Invalid structured input",
            "errors": [{"loc": item["loc"], "type": item["type"]} for item in error.errors()],
        },
        status_code=422,
    )


class Credentials(Model):
    email: str = Field(default="broker@helm.demo", max_length=200)
    password: str = Field(min_length=1, max_length=256)


class StepUp(Model):
    password: str = Field(min_length=1, max_length=256)


class Action(Model):
    reason: str = Field(default="", max_length=1000)
    dnr_acknowledged: bool = False
    vulnerability_acknowledged: bool = False
    underwriter_reference: str = Field(default="", max_length=200)
    scenario: Scenario = "happy"
    medical_released: bool = False
    ranking_id: str = ""
    selected: list[str] = Field(default_factory=list, max_length=3)
    survey: Survey | None = None
    acknowledgements: list[str] = Field(default_factory=list)
    suitability: str | None = Field(default=None, max_length=20000)
    pack_hash: str = ""
    step_up_token: str = ""


class EditDNR(Model):
    dnr: DNR
    reason: str = Field(min_length=3, max_length=500)


class SuitabilityEdit(Model):
    text: str = Field(min_length=20, max_length=20000)
    dnr_sections_confirmed: list[str] = Field(default_factory=list)
    unmet_needs_addressed: list[str] = Field(default_factory=list)
    suitability_confirmed_plans: list[str] = Field(default_factory=list, max_length=3)
    overall_suitability_confirmed: bool = False


# shortcut: per-process login throttle for a local demo; replace with shared Redis limits before live use.
attempts = {}


@app.get("/health")
def health(db=Depends(database, scope="function")):
    from app.platform_api import readiness

    response = readiness(db)
    body = json.loads(response.body)
    return JSONResponse(
        {**body, "version": "0.1.0", "mode": settings().mode, "agent_runtime": settings().agent_runtime},
        status_code=response.status_code,
    )


@app.post("/api/v1/auth/password")
def login(body: Credentials, request: Request, response: Response, db=Depends(database, scope="function")):
    address = request.client.host if request.client else "local"
    now = utcnow().timestamp()
    attempts[address] = [t for t in attempts.get(address, []) if t > now - 60]
    if len(attempts[address]) >= 10:
        raise DomainError("Too many attempts; try again in a minute", 429)
    attempts[address].append(now)
    user = authenticate(db, body.email, body.password)
    session, token = new_session(db, user)
    response.set_cookie(
        "helm_session",
        token,
        httponly=True,
        secure=settings().cookie_secure,
        samesite="strict",
        max_age=settings().session_hours * 3600,
        path="/",
    )
    return {"user": public_user(user), "csrf": session.csrf}


@app.get("/api/v1/auth/session")
def session(request: Request, db=Depends(database, scope="function")):
    user, session = identity(db, request)
    return {"user": public_user(user), "csrf": session.csrf}


@app.post("/api/v1/auth/logout")
def logout(request: Request, response: Response, db=Depends(database, scope="function")):
    _, session = identity(db, request)
    db.delete(session)
    response.delete_cookie("helm_session", path="/")
    return {"ok": True}


@app.post("/api/v1/auth/step-up")
def step_up(body: StepUp, request: Request, db=Depends(database, scope="function")):
    user, session = identity(db, request)
    if not verify_password(body.password, user.password_hash):
        raise DomainError("Password is incorrect", 401)
    session.step_up_at = utcnow().isoformat()
    return {"ok": True, "expires_in": 300}


@app.get("/api/v1/agents")
def agents(request: Request, db=Depends(database, scope="function")):
    identity(db, request)
    return {"agents": AGENTS, "runtime": settings().agent_runtime, "llm_enabled": False}


@app.get("/api/v1/partners")
def partners(request: Request, db=Depends(database, scope="function")):
    identity(db, request)
    from app.db.platform import Partner

    return [
        {
            key: getattr(p, key)
            for key in ("id", "name", "fca_status", "toba_status", "fictional", "is_active")
        }
        for p in db.scalars(select(Partner).order_by(Partner.id))
    ]


@app.get("/api/v1/cases")
def cases(request: Request, q: str = "", state: str = "", db=Depends(database, scope="function")):
    identity(db, request)
    service.process_due_jobs(db)
    rows = db.scalars(select(Case).order_by(Case.created_at.desc())).all()
    return [
        {
            "id": c.id,
            **c.profile,
            "state": c.state,
            "created_at": c.created_at,
            "assigned_to": c.assigned_to,
            "version": c.version,
        }
        for c in rows
        if (not q or q.lower() in c.profile["name"].lower()) and (not state or c.state == state)
    ]


@app.post("/api/v1/demo/requests")
def create_demo_request(body: QuoteRequest, request: Request, db=Depends(database, scope="function")):
    user, _ = identity(db, request)
    service.require_broker(user)
    return safe_case(service.detail(db, service.import_request(db, body)), user)


@app.get("/api/v1/cases/{case_id}")
def case_detail(
    case_id: str, request: Request, include_medical: bool = False, db=Depends(database, scope="function")
):
    user, session = identity(db, request)
    case = service.get_case(db, case_id)
    service.process_due_jobs(db)
    if include_medical:
        from app.medical_access import require_medical_access

        require_medical_access(db, case, user, session)
    return safe_case(service.detail(db, case), user, include_medical)


@app.patch("/api/v1/cases/{case_id}/dnr")
def edit_dnr(case_id: str, body: EditDNR, request: Request, db=Depends(database, scope="function")):
    user, _ = identity(db, request)
    service.require_broker(user)
    case = service.get_case(db, case_id)
    if case.state not in (State.NEEDS_INFO, State.FACTFIND_REVIEW, State.AWAIT_BROKER_RELEASE):
        raise DomainError("Return the case to fact-find review before changing requirements")
    previous = latest(db, case_id, "dnr")
    if body.dnr.version != previous.version:
        raise DomainError("This fact-find changed. Reload before editing again.", 409)
    if body.dnr.request_id != previous.body["request_id"]:
        raise DomainError("Request identity cannot be changed", 422)
    revised = body.dnr.model_copy(update={"version": previous.version + 1})
    revised.medical_items = previous.body["medical_items"]
    revised.facts = {key: Fact.model_validate(value) for key, value in previous.body["facts"].items()}
    for field, value in revised.needs.model_dump().items():
        if value == previous.body["needs"].get(field):
            continue
        revised.facts[field] = Fact(
            value=value,
            source=f"broker_edit:{case_id}:v{revised.version}",
            verified_by=user.id,
        )
    from app.schemas import DNRRecord

    if previous.body.get("record"):
        revised.record = DNRRecord.model_validate(previous.body["record"])
    else:
        from app.agents.intake import research_request

        revised.record = research_request(
            QuoteRequest.model_validate(latest(db, case_id, "request").body)
        ).record
    if revised.record:
        revised.record.budget_confirmed, revised.record.broker_ref = False, None
        revised.record.stated_needs = [
            {
                "category": key,
                "detail": str(value),
                "source": "client" if value == previous.body["needs"].get(key) else f"broker:{user.id}",
            }
            for key, value in revised.needs.model_dump().items()
        ]
    if not revised.consent_to_share and "consent_to_share" not in revised.missing:
        revised.missing.append("consent_to_share")
    if not revised.needs.coverage and "desired_coverage" not in revised.missing:
        revised.missing.append("desired_coverage")
    save_snapshot(db, case_id, "dnr", revised.model_dump())
    save_snapshot(db, case_id, "dnr_edit", {"reason": body.reason, "by": user.id, "version": revised.version})
    service.transition(
        db,
        case,
        [case.state],
        State.NEEDS_INFO if revised.missing else State.FACTFIND_REVIEW,
        "dnr_revised",
        f"broker:{user.id}",
        {"version": revised.version},
    )
    return safe_case(service.detail(db, case), user)


from app.case_operations import router as case_operations_router  # noqa: E402

app.include_router(case_operations_router)
from app.medical_access import router as medical_router  # noqa: E402

app.include_router(medical_router)
from app.plan_ratings import router as ratings_router  # noqa: E402

app.include_router(ratings_router)


@app.post("/api/v1/cases/{case_id}/{action}")
def case_action(
    case_id: str,
    action: Literal[
        "sign-off",
        "release",
        "selection",
        "approve",
        "publish",
        "pause",
        "resume",
        "assign",
        "request-changes",
        "complaint",
        "resolve",
    ],
    body: Action,
    request: Request,
    db=Depends(database, scope="function"),
):
    user, session = identity(db, request)
    if action == "selection" and body.survey is None:
        raise DomainError("Selection requires the short survey", 422)
    return safe_case(
        service.act(
            db, case_id, "approve" if action == "publish" else action, user, session, body.model_dump()
        ),
        user,
    )


@app.put("/api/v1/cases/{case_id}/suitability")
def edit_suitability(
    case_id: str, body: SuitabilityEdit, request: Request, db=Depends(database, scope="function")
):
    user, _ = identity(db, request)
    service.require_broker(user)
    case = service.get_case(db, case_id)
    if case.state != State.AWAIT_APPROVAL:
        raise DomainError("Only a draft awaiting approval can be edited")
    previous = latest(db, case_id, "pack").body
    revised = {k: v for k, v in previous.items() if k != "pack_hash"}
    revised["suitability_final"] = body.text.strip()
    revised["review_saved_at"] = utcnow().isoformat()
    revised["dnr_sections_confirmed"] = body.dnr_sections_confirmed
    revised["unmet_needs_addressed"] = body.unmet_needs_addressed
    revised["suitability_confirmed_plans"] = body.suitability_confirmed_plans
    revised["overall_suitability_confirmed"] = body.overall_suitability_confirmed
    import difflib

    revised["suitability_diff"] = list(
        difflib.unified_diff(previous["suitability_draft"].splitlines(), body.text.strip().splitlines())
    )
    revised["pack_hash"] = canonical_hash(revised)
    save_snapshot(db, case_id, "pack", revised)
    audit(db, case_id, "suitability_edited", f"broker:{user.id}", {"pack_hash": revised["pack_hash"]})
    return safe_case(service.detail(db, case), user)


@app.get("/api/v1/cases/{case_id}/evidence")
def export_evidence(case_id: str, request: Request, db=Depends(database, scope="function")):
    user, session = identity(db, request)
    case = service.get_case(db, case_id)
    from app.evidence import generate, pdf_bytes

    include_medical = request.query_params.get("include_medical") == "true"
    if include_medical:
        from app.medical_access import require_medical_access

        require_medical_access(db, case, user, session)
    result = generate(db, case, user, include_medical)
    audit(db, case_id, "evidence_exported", f"user:{user.id}")
    if "application/pdf" in request.headers.get("accept", ""):
        return Response(
            pdf_bytes(result),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="helm-evidence-{case_id}.pdf"'},
        )
    return result


@app.get("/api/v1/cases/{case_id}/stream")
async def stream(case_id: str, request: Request, after: int = 0, db=Depends(database, scope="function")):
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
                rows = connection.scalars(
                    select(Activity)
                    .where(Activity.case_id == case_id, Activity.seq > cursor)
                    .order_by(Activity.seq)
                ).all()
                for row in rows:
                    cursor = row.seq
                    data = {"type": row.type, "seq": row.seq, "payload": row.payload}
                    yield f"id: {row.seq}\ndata: {json.dumps(data)}\n\n"
            yield ": heartbeat\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(events(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})


@app.get("/api/v1/models")
def models(request: Request, db=Depends(database, scope="function")):
    identity(db, request)
    return [
        {"id": m.id, "created_at": m.created_at, **m.body, "status": m.status}
        for m in db.scalars(select(ModelProposal).order_by(ModelProposal.created_at.desc())).all()
    ]


@app.post("/api/v1/models/evaluate")
def evaluate(request: Request, db=Depends(database, scope="function")):
    user, _ = identity(db, request)
    if user.role not in ("authorised_broker", "compliance_officer"):
        raise DomainError("Only advisers and compliance may run an evaluation", 403)
    return service.learning_run(db)


from app.platform_api import router as platform_router  # noqa: E402

app.include_router(platform_router)
from app.auth.router import router as auth_router  # noqa: E402

app.router.routes = [
    route for route in app.router.routes if not getattr(route, "path", "").startswith("/api/v1/auth/")
]
app.include_router(auth_router)
from app.live import router as live_router  # noqa: E402

app.router.routes = [
    route for route in app.router.routes if not getattr(route, "path", "").endswith("/stream")
]
app.include_router(live_router)
from app.governance_api import router as governance_router  # noqa: E402

app.include_router(governance_router)
from app.insights_api import router as insights_router  # noqa: E402

app.include_router(insights_router)
from app.observability import instrument  # noqa: E402

from app.case_queries import router as case_queries_router  # noqa: E402

app.router.routes = [
    r
    for r in app.router.routes
    if not (getattr(r, "path", "") == "/api/v1/cases" and "GET" in getattr(r, "methods", set()))
]
app.include_router(case_queries_router)


_application_template = app


def create_app():
    """Build an independent ASGI stack from the registered, stateless route definitions."""
    documentation_paths = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
    application = FastAPI(
        title=_application_template.title,
        version=_application_template.version,
        description=_application_template.description,
        lifespan=lifespan,
        routes=[
            route
            for route in _application_template.routes
            if getattr(route, "path", None) not in documentation_paths
        ],
        middleware=list(_application_template.user_middleware),
        exception_handlers=dict(_application_template.exception_handlers),
    )
    instrument(application)
    return application


app = create_app()
