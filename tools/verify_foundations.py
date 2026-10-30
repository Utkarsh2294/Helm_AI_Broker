"""Verify P0 on dedicated loopback QA ports using fictional partner computations."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
import httpx

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "services/api"))
from app.agents.quotation import PARTNERS  # noqa: E402


def verify():
    health = httpx.get("http://127.0.0.1:8014/health", timeout=15)
    health.raise_for_status()
    assert health.json()["db"] == health.json()["redis"] == "ok"
    simulator = httpx.get("http://127.0.0.1:8013/health", timeout=15)
    simulator.raise_for_status()
    counts = {}
    for partner in PARTNERS:
        response = httpx.post("http://127.0.0.1:8013/rfq", json={"partner_id": partner["id"]}, timeout=15)
        response.raise_for_status()
        assert response.json()["fictional"]
        counts[partner["id"]] = len(response.json()["quotes"])
    assert len(counts) == 5 and sum(counts.values()) == 30
    result = {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "verified": True,
        "api_health": health.json(),
        "standalone_simulator": simulator.json(),
        "quotes_by_fictional_partner": counts,
        "real_insurer_requests": False,
    }
    (root / "docs/verification/main-plan-p0.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf8"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    verify()
