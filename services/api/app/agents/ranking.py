"""A3: deterministic ranking and grounded explanations, with immutable inputs."""

import hashlib
import json
from decimal import Decimal
from app.engine.ranking import rank_plans
from app.schemas import DNR, Plan
from app.agents.guards import consumer_draft, grounded


def rank_quotes(
    dnr: DNR, quotes: list[Plan], ranking_id: str, learned=None, tax_rate=Decimal("0.12")
) -> dict:
    inputs = {"dnr": dnr.model_dump(), "quotes": [q.model_dump() for q in sorted(quotes, key=lambda q: q.id)]}
    result = rank_plans(quotes, dnr.needs, ranking_id, learned, tax_rate)
    for row in result["top"]:
        row["consumer_draft"] = consumer_draft(row["plan"])
        row["explanation_grounded"] = grounded(row["explanation"], row)
        row["consumer_draft_grounded"] = grounded(row["consumer_draft"], row)
    result.update(
        {
            "id": ranking_id,
            "dnr_version": dnr.version,
            "inputs_hash": hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest(),
        }
    )
    return result
