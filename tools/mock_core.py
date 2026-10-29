"""Standalone fictional consumer Core API. Never sends real emails."""
import base64
import hashlib
import secrets
import time
from datetime import timedelta
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
import httpx
import jwt
from app.agents.quotation import PARTNERS, RFQ, simulate_responses, premium_with_tax
from app.config import settings
from app.core_client.client import encode_event, sign
from app.db.models import stamp, utcnow
from app.schemas import CoverageNeed, Needs, QuoteRequest

app = FastAPI(title="Helm fictional Core", version="1.0.0")
requests = {f"core-{i}": QuoteRequest(id=f"core-{i}", name=name, cover_type=cover,
    needs=Needs(coverage={"cancer": CoverageNeed(level=3, must_have=True),
        "outpatient": CoverageNeed(level=2)})).model_dump()
    for i, (name, cover) in enumerate([( "Asha Patel", "family"), ("Oliver Bennett", "individual"),
                                      ("Sophie and James", "couple")], 1)}
rfqs, recommendations, idempotency, magic_tokens = {}, {}, {}, {}


def catalogue():
    rfq = RFQ(request_id="catalogue", dnr_version=1, deadline=utcnow(), partners=[p["id"] for p in PARTNERS], body={})
    base, _ = simulate_responses(rfq)
    plans = []
    for plan in base:
        for variant in range(3):
            copy = plan.model_copy(deep=True)
            copy.id += f"-{variant}"
            copy.name += f" {['Standard', 'Select', 'Complete'][variant]}"
            copy.basePremiumPence += variant * 6500
            copy.annualPremiumPence = premium_with_tax(copy.basePremiumPence, settings().ipt_standard_rate)
            copy.excessPence = [0, 25000, 50000][variant]
            plans.append(copy.model_dump())
    return plans


def problem(message, status=400):
    return JSONResponse({"type": "about:blank", "title": message, "detail": message, "status": status},
                        status_code=status, media_type="application/problem+json")


@app.middleware("http")
async def boundary(request: Request, call_next):
    if request.url.path.startswith("/v1/"):
        try:
            jwt.decode(request.headers.get("Authorization", "").removeprefix("Bearer "),
                       settings().secret_key, algorithms=["HS256"], audience="mock-core")
        except jwt.PyJWTError:
            return problem("Invalid service credential", 401)
        if request.method == "POST" and not request.headers.get("Idempotency-Key"):
            return problem("Idempotency-Key is required", 422)
    return await call_next(request)


@app.post("/oauth/token")
def token(body: dict):
    if not secrets.compare_digest(body.get("client_secret", ""), settings().core_client_secret) or body.get("client_id") != settings().core_client_id:
        return problem("Invalid client credentials", 401)
    return {"access_token": jwt.encode({"aud": "mock-core", "sub": body["client_id"], "exp": time.time() + 300},
                                      settings().secret_key, algorithm="HS256"), "token_type": "Bearer"}


def page(rows, cursor="", limit=20):
    try:
        start = int(base64.urlsafe_b64decode(cursor).decode()) if cursor else 0
    except (ValueError, UnicodeDecodeError):
        return problem("Invalid cursor", 422)
    limit = min(100, max(1, limit))
    return {"items": rows[start:start + limit], "next_cursor":
            base64.urlsafe_b64encode(str(start + limit).encode()).decode() if start + limit < len(rows) else None}


@app.get("/health")
def health():
    return {"status": "ok", "fictional": True}


@app.get("/v1/quote-requests")
def list_requests(cursor: str = "", limit: int = 20):
    return page(list(requests.values()), cursor, limit)


@app.get("/v1/quote-requests/{request_id}")
def request_detail(request_id: str):
    return requests.get(request_id) or problem("Request not found", 404)


@app.get("/v1/quote-requests/{request_id}/documents/{document_id}")
def document(request_id: str, document_id: str):
    return {"id": document_id, "request_id": request_id, "text": "Fictional renewal. Annual premium GBP 1200.", "expires_in": 300}


@app.post("/v1/quote-requests/{request_id}/info-requests")
def info_request(request_id: str, body: dict):
    return {"id": secrets.token_hex(12), "request_id": request_id, "status": "demo_recorded"}


@app.get("/v1/partners")
def partners(cursor: str = "", limit: int = 20):
    return page(PARTNERS, cursor, limit)


@app.get("/v1/partners/{partner_id}")
def partner(partner_id: str):
    return next((p for p in PARTNERS if p["id"] == partner_id), None) or problem("Partner not found", 404)


@app.get("/v1/catalogue/plans")
def plans(cursor: str = "", limit: int = 20):
    return page(catalogue(), cursor, limit)


@app.post("/v1/rfqs")
def create_rfq(body: dict, idempotency_key: str = Header()):
    if idempotency_key in idempotency:
        return idempotency[idempotency_key]
    rfq_id = secrets.token_hex(12)
    rfq = RFQ(request_id=body.get("request_id", "demo"), dnr_version=1,
              deadline=utcnow() + timedelta(seconds=8), partners=[p["id"] for p in PARTNERS], body=body)
    scenario = {f"S{i}": value for i, value in enumerate(["happy", "decline", "late", "arithmetic", "medical", "duplicate", "referral", "injection"], 1)}
    quotes, board = simulate_responses(rfq, scenario.get(body.get("scenario", "S1"), "happy"))
    rfqs[rfq_id] = {"id": rfq_id, "quotes": [p.model_dump() for p in quotes], "partners": board, "status": "answered"}
    idempotency[idempotency_key] = rfqs[rfq_id]
    return rfqs[rfq_id]


@app.get("/v1/rfqs/{rfq_id}")
@app.get("/v1/rfqs/{rfq_id}/responses")
def responses(rfq_id: str):
    return rfqs.get(rfq_id) or problem("RFQ not found", 404)


@app.post("/v1/rfqs/{rfq_id}/messages")
def rfq_message(rfq_id: str, body: dict):
    return {"id": secrets.token_hex(12), "status": "demo_recorded"}


@app.post("/v1/recommendations")
def publish(body: dict, idempotency_key: str = Header()):
    if idempotency_key in idempotency:
        return idempotency[idempotency_key]
    if not body.get("approval_id") or not body.get("pack", {}).get("pack_hash"):
        return problem("Human approval and immutable pack required", 422)
    rec_id, raw = secrets.token_hex(12), secrets.token_urlsafe(32)
    result = {"recommendation_id": rec_id, "magic_link_sent": False, "demo": True,
              "magic_link": f"http://127.0.0.1:8011/magic/{raw}", "status": "demo_delivered"}
    recommendations[rec_id] = {**body, **result}
    magic_tokens[hashlib.sha256(raw.encode()).hexdigest()] = {"id": rec_id, "expires": time.time() + 48 * 3600, "used": False}
    idempotency[idempotency_key] = result
    return result


@app.get("/magic/{raw}")
def magic(raw: str):
    record = magic_tokens.get(hashlib.sha256(raw.encode()).hexdigest())
    if not record or record["used"] or record["expires"] < time.time():
        return problem("Expired or used link", 410)
    record["used"] = True
    return {"demo": True, "recommendation_id": record["id"], "message": "Fictional consumer handoff preview"}


@app.post("/v1/recommendations/{rec_id}/revoke")
def revoke(rec_id: str):
    if rec_id not in recommendations:
        return problem("Recommendation not found", 404)
    for token in magic_tokens.values():
        if token["id"] == rec_id:
            token["used"] = True
    return {"status": "revoked"}


@app.post("/v1/messages")
def message(body: dict):
    if not body.get("approved_by"):
        return problem("Broker-approved message required", 403)
    return {"status": "demo_recorded", "id": secrets.token_hex(12)}


@app.post("/demo/submit/{request_id}")
async def submit(request_id: str):
    if request_id not in requests:
        return problem("Request not found", 404)
    event = {"id": secrets.token_hex(16), "type": "quote_request.submitted", "request": requests[request_id]}
    body, timestamp = encode_event(event), str(int(time.time()))
    async with httpx.AsyncClient() as client:
        response = await client.post("http://api:8010/api/v1/webhooks/core", content=body,
            headers={"X-Helm-Signature": sign(body, timestamp, settings().core_webhook_secret),
                     "X-Helm-Timestamp": timestamp, "Content-Type": "application/json"})
        return {"status": response.status_code, "event_id": event["id"]}
