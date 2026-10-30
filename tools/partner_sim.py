"""Standalone, fictional partner channel. Controls require the local simulator key."""

import asyncio
import secrets
from typing import Literal
from fastapi import FastAPI, Header, HTTPException
from pydantic import Field
from app.agents.quotation import PARTNERS, RFQ, Scenario, simulate_responses
from app.clock import wall_now
from app.config import settings
from app.schemas import Model, Plan

app = FastAPI(title="Helm fictional partner simulator", version="0.1.0")
responses = {}


class SimRequest(Model):
    partner_id: str = Field(max_length=100)
    rfq: RFQ | None = None
    scenario: Scenario = "happy"


class SimControl(Model):
    partner_id: str = Field(max_length=100)
    type: Literal["quote", "timeout", "referral", "error"]
    delay_ms: int = Field(default=0, ge=0, le=8000)


class SimReply(Model):
    partner_id: str
    state: str
    fictional: bool = True
    quotes: list[Plan]


def known_partner(partner_id):
    if partner_id not in {p["id"] for p in PARTNERS}:
        raise HTTPException(404, "Unknown fictional partner")


@app.get("/health")
def health():
    return {"status": "ok", "fictional": True, "partners": len(PARTNERS)}


@app.post("/rfq", response_model=SimReply)
async def rfq(body: SimRequest):
    known_partner(body.partner_id)
    control = responses.get(body.partner_id)
    if control:
        await asyncio.sleep(control.delay_ms / 1000)
        if control.type == "error":
            raise HTTPException(503, "Fictional partner failure")
        if control.type != "quote":
            return SimReply(partner_id=body.partner_id, state=control.type, quotes=[])
    request = body.rfq or RFQ(
        request_id="simulator", dnr_version=1, deadline=wall_now(), partners=[body.partner_id], body={}
    )
    plans, board = simulate_responses(request, body.scenario, settings().ipt_standard_rate)
    partner = next((p for p in board if p["id"] == body.partner_id), None)
    if partner is None:
        raise HTTPException(422, "Partner is absent from this RFQ")
    return SimReply(
        partner_id=body.partner_id,
        state=partner["state"],
        quotes=[p for p in plans if p.insurerId == body.partner_id],
    )


@app.post("/rfq/set-response")
def configure_response(body: SimControl, x_simulator_key: str = Header(default="")):
    if settings().clock_mode != "demo" or not secrets.compare_digest(
        x_simulator_key, settings().core_client_secret
    ):
        raise HTTPException(403, "Simulator controls require the local demo key")
    known_partner(body.partner_id)
    responses[body.partner_id] = body
    return {"configured": body.partner_id, "fictional": True}
