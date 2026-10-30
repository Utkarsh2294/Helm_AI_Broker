"""Exercise real local API/partner HTTP processes with fictional, controlled responses."""

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/api"))
from app.config import settings  # noqa: E402
from app.agents.quotation import PARTNERS  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8012")
    parser.add_argument("--simulator", default="http://127.0.0.1:8015")
    parser.add_argument("--output", default="docs/verification/main-plan-p4.json")
    args = parser.parse_args()
    assert all(urlsplit(url).hostname in {"localhost", "127.0.0.1"} for url in (args.api, args.simulator))
    with (
        httpx.Client(base_url=args.api, timeout=20) as api,
        httpx.Client(base_url=args.simulator, timeout=5) as sim,
    ):
        assert api.get("/health").json()["mode"] == "demo"
        login = api.post(
            "/api/v1/auth/password", json={"email": "broker@helm.demo", "password": "HelmDemo!2026"}
        )
        login.raise_for_status()
        api.headers["X-CSRF-Token"] = login.json()["csrf"]

        def control(partner, kind="quote", delay=0):
            response = sim.post(
                "/rfq/set-response",
                json={"partner_id": partner, "type": kind, "delay_ms": delay},
                headers={"X-Simulator-Key": settings().core_client_secret},
            )
            response.raise_for_status()

        def reset():
            for partner in PARTNERS:
                control(partner["id"])

        def run():
            created = api.post(
                "/api/v1/demo/requests",
                json={
                    "id": f"p4-network-{time.time_ns()}",
                    "name": "Fictional HTTP pipeline fixture",
                    "needs": {"coverage": {"outpatient": {"level": 2}}},
                },
            )
            created.raise_for_status()
            case = created.json()
            url = "/api/v1/cases/" + case["id"]
            signed = api.post(url + "/sign-off", json={"dnr_acknowledged": True})
            signed.raise_for_status()
            started = time.monotonic()
            released = api.post(url + "/release", json={})
            released.raise_for_status()
            while time.monotonic() - started < 15:
                detail = api.get(url)
                detail.raise_for_status()
                case = detail.json()
                if case["state"] != "QUOTES_PENDING":
                    break
                time.sleep(0.05)
            return case, round(time.monotonic() - started, 3)

        results = {}
        try:
            reset()
            case, elapsed = run()
            assert case["state"] == "BROKER_REVIEW"
            assert len(case["quotes"]["quotes"]) == 30 and len(case["quotes"]["partners"]) == 5
            assert elapsed < 10
            results["happy"] = {"seconds": elapsed, "quotes": 30, "partners": 5, "state": case["state"]}
            control("alder", delay=8000)
            case, elapsed = run()
            assert case["state"] == "BROKER_REVIEW" and len(case["quotes"]["quotes"]) == 24
            assert next(p for p in case["quotes"]["partners"] if p["id"] == "alder")["state"] == "timed_out"
            assert elapsed < 10
            results["one_real_http_timeout"] = {"seconds": elapsed, "quotes": 24, "state": case["state"]}
            for partner in PARTNERS:
                control(partner["id"], "timeout")
            case, elapsed = run()
            assert case["state"] == "PAUSED_NEEDS_HUMAN" and case["ranking"] is None
            results["insufficient_quotes"] = {"seconds": elapsed, "quotes": 0, "state": case["state"]}
            reset()
            control("alder", "referral")
            case, elapsed = run()
            assert case["state"] == "UW_REFERRAL"
            results["referral"] = {"seconds": elapsed, "state": case["state"]}
        finally:
            reset()
    report = {"fictional_only": True, "transport": "actual independent HTTP processes", "checks": results}
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
