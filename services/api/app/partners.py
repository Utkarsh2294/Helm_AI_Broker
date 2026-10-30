"""Deterministic classification and the simulator/Core Workspace delivery boundary."""

import re
import asyncio
import logging
from datetime import timedelta
from types import SimpleNamespace
import httpx
from pydantic import ValidationError
from sqlalchemy import select
from app.clock import get_clock
from app.agents.quotation import PARTNERS
from app.schemas import DomainError
from app.agents.quotation import simulate_responses, normalise_responses
from app.config import settings
from app.core_client.client import CoreAPIClient
from app.schemas import Plan

INJECTION = re.compile(
    r"ignore\s+(all\s+)?previous|system\s+prompt|assistant\s*:|you are now|drop\s+table|<script|[\u202a-\u202e]|\"role\"\s*:\s*\"(?:system|assistant)\"",
    re.I,
)
HEALTH = re.compile(r"health|medical|condition|symptom|medication|diagnos|treatment|cancer|breathless", re.I)


def classify_reply(text):
    injected = bool(INJECTION.search(text))
    label = "other"
    if not injected:
        if re.search(r"declin|cannot quote|outside appetite", text, re.I):
            label = "decline"
        elif re.search(r"refer|counter.term|underwriter review", text, re.I):
            label = "referral"
        elif re.search(r"clarif|please confirm|more information|\?", text, re.I):
            label = "clarification"
        elif re.search(r"quote|premium|annual", text, re.I):
            label = "quote"
    return {
        "label": label,
        "confidence": 1.0,
        "contains_health_info": bool(HEALTH.search(text)),
        "injected_flag": injected,
    }


def active_partners(db, dnr=None):
    from app.db.platform import Partner

    rows = db.scalars(
        select(Partner).where(
            Partner.is_active.is_(True), Partner.fca_status == "authorised", Partner.toba_status == "active"
        )
    ).all()
    if not dnr:
        return rows
    members = 1 if dnr.facts["cover_type"].value == "individual" else 2
    return [
        p
        for p in rows
        if p.max_members >= members
        and any(
            (method == "moratorium" and p.supports_moratorium) or (method == "FMU" and p.supports_fmu)
            for method in dnr.needs.allowed_underwriting
        )
    ]


class PartnerGateway:
    def __init__(self, transport=None, clock=None):
        self.transport, self.clock = transport, clock or get_clock()

    async def _fan_out(self, rfq, scenario, partners):
        async with httpx.AsyncClient(
            base_url=settings().partner_simulator_url, transport=self.transport
        ) as client:

            async def send(partner):
                timeout = self.clock.wall_delay(timedelta(seconds=partner.timeout_seconds)).total_seconds()
                try:

                    async def request():
                        for attempt in range(2):
                            try:
                                reply = await client.post(
                                    partner.api_endpoint,
                                    json={
                                        "partner_id": partner.id,
                                        "rfq": rfq.model_dump(mode="json"),
                                        "scenario": scenario,
                                    },
                                    timeout=timeout,
                                    headers={
                                        "Idempotency-Key": f"rfq:{rfq.request_id}:{rfq.dnr_version}:{partner.id}"
                                    },
                                )
                            except httpx.TransportError:
                                if attempt:
                                    raise
                                continue
                            if reply.status_code < 500 or attempt:
                                return reply

                    response = await asyncio.wait_for(request(), timeout=timeout)
                    response.raise_for_status()
                    result = response.json()
                    if (
                        not isinstance(result, dict)
                        or result.get("partner_id") != partner.id
                        or not isinstance(result.get("quotes"), list)
                        or len(result["quotes"]) > 100
                    ):
                        raise ValueError("Invalid response envelope")
                    plans = [Plan.model_validate(p) for p in result["quotes"]]
                    if any(p.insurerId != partner.id for p in plans):
                        raise ValueError("Unexpected insurer")
                    state = result["state"]
                    if state == "late":
                        state = "timed_out"
                    if state not in {
                        "quoted",
                        "declined",
                        "timeout",
                        "timed_out",
                        "clarification",
                        "referred",
                        "referral",
                    }:
                        raise ValueError("Invalid response state")
                    if state in {"timeout", "timed_out", "declined", "referred", "referral", "clarification"}:
                        plans = []
                    return plans, {
                        "id": partner.id,
                        "name": partner.name,
                        "state": "referred" if state == "referral" else state,
                    }
                except (TimeoutError, httpx.TimeoutException):
                    state = "timed_out"
                except (httpx.HTTPError, ValidationError, ValueError, KeyError, TypeError):
                    state = "invalid"
                logging.getLogger("helm.partners").warning(
                    "partner_response_rejected", extra={"partner_id": partner.id, "state": state}
                )
                return [], {"id": partner.id, "name": partner.name, "state": state}

            replies = await asyncio.gather(
                *(send(partner) for partner in partners if partner.id in rfq.partners)
            )
        return [plan for plans, _ in replies for plan in plans], [row for _, row in replies]

    async def collect(self, rfq, scenario, partners=None):
        if settings().partner_mode == "simulator":
            plans, board = simulate_responses(rfq, scenario, settings().ipt_standard_rate)
        elif settings().partner_mode == "http_simulator":
            partners = (
                partners
                if partners is not None
                else [SimpleNamespace(**p, timeout_seconds=21600, api_endpoint="/rfq") for p in PARTNERS]
            )
            plans, board = await self._fan_out(rfq, scenario, partners)
        else:
            result = await CoreAPIClient().request(
                "POST",
                "/v1/rfqs",
                {**rfq.model_dump(mode="json"), "scenario": scenario},
                key=f"rfq:{rfq.request_id}:{rfq.dnr_version}",
            )
            plans = [Plan.model_validate(plan) for plan in result["quotes"]]
            board = result["partners"]
        if any(p.insurerId not in rfq.partners for p in plans):
            raise DomainError("H7: response from an unrequested partner", 422)
        return {
            "quotes": [p.model_dump() for p in normalise_responses(plans)],
            "raw_quotes": [p.model_dump() for p in plans],
            "partners": board,
        }
