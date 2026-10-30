"""Short, rehydratable steps. CaseService owns gates and durable state."""

import os
from importlib import import_module
from opentelemetry import trace
from decimal import Decimal
from app.agents.intake import research_request
from app.agents.quotation import RFQ, normalise_responses, simulate_responses
from app.agents.ranking import rank_quotes
from app.agents.review import assemble_pack
from app.agents.learning import propose_improvement
from app.schemas import DNR, Plan, QuoteRequest, Survey

AGENTS = [
    {
        "id": 1,
        "name": "Research & fact-find",
        "purpose": "Ground requirements in source facts",
        "key": "intake",
    },
    {
        "id": 2,
        "name": "Partner quotations",
        "purpose": "Request and normalise partner quotations",
        "key": "quotation",
    },
    {"id": 3, "name": "Policy ranking", "purpose": "Compute scores and explain trade-offs", "key": "ranking"},
    {
        "id": 4,
        "name": "Review & compliance",
        "purpose": "Draft the broker's recommendation pack",
        "key": "review",
    },
    {
        "id": 5,
        "name": "Learning & insights",
        "purpose": "Propose bounded improvements from feedback",
        "key": "learning",
    },
]


def prepare_runtime(runtime):
    if runtime == "crewai":
        os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")
        os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
        import_module("crewai.flow.flow")


def execute_step(kind, payload):
    if kind == "intake":
        return research_request(QuoteRequest.model_validate(payload)).model_dump(mode="json")
    if kind == "quotation":
        plans, board = simulate_responses(
            RFQ.model_validate(payload["rfq"]), payload["scenario"], Decimal(payload.get("tax_rate", "0.12"))
        )
        return {
            "quotes": [p.model_dump() for p in normalise_responses(plans)],
            "raw_quotes": [p.model_dump() for p in plans],
            "partners": board,
        }
    if kind == "ranking":
        return rank_quotes(
            DNR.model_validate(payload["dnr"]),
            [Plan.model_validate(p) for p in payload["quotes"]],
            payload["id"],
            learned=payload.get("learned"),
            tax_rate=Decimal(payload.get("tax_rate", "0.12")),
        )
    if kind == "review":
        return assemble_pack(
            DNR.model_validate(payload["dnr"]),
            payload["ranking"],
            payload["selected"],
            Survey.model_validate(payload["survey"]),
            payload["acknowledgements"],
            payload.get("suitability"),
        )
    if kind == "learning":
        return propose_improvement(
            payload["records"], payload.get("champion"), payload.get("min_comparisons", 30)
        )
    raise ValueError("Unknown agent")


@trace.get_tracer("helm.agents").start_as_current_span("agent.step", record_exception=False)
def run_agent(kind, payload, runtime="python"):
    trace.get_current_span().set_attribute("helm.agent", kind)
    if runtime == "python":
        return execute_step(kind, payload)
    # Framework runs local code-only steps. No LLM receives consumer health text.
    os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")
    os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
    from crewai.flow.flow import Flow, start
    from pydantic import BaseModel, Field

    class StepState(BaseModel):
        kind: str = ""
        payload: dict = Field(default_factory=dict)

    class BrokerStep(Flow[StepState]):
        @start()
        def execute(self):
            return execute_step(self.state.kind, self.state.payload)

    return BrokerStep(tracing=False).kickoff(inputs={"kind": kind, "payload": payload})
