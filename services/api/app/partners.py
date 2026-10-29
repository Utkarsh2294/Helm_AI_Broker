"""Deterministic classification and the simulator/Core Workspace delivery boundary."""

import re
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


class PartnerGateway:
    async def collect(self, rfq, scenario):
        if settings().partner_mode == "simulator":
            plans, board = simulate_responses(rfq, scenario, settings().ipt_standard_rate)
        else:
            result = await CoreAPIClient().request(
                "POST",
                "/v1/rfqs",
                {**rfq.model_dump(mode="json"), "scenario": scenario},
                key=f"rfq:{rfq.request_id}:{rfq.dnr_version}",
            )
            plans = [Plan.model_validate(plan) for plan in result["quotes"]]
            board = result["partners"]
        return {
            "quotes": [p.model_dump() for p in normalise_responses(plans)],
            "raw_quotes": [p.model_dump() for p in plans],
            "partners": board,
        }
