"""Verify actual service-to-service delivery using fictional data and dedicated QA ports."""

import argparse
import json
import time
from pathlib import Path
from uuid import uuid4
import httpx


def checked(response):
    response.raise_for_status()
    return response.json()


def verify(base_url, output, timeout_seconds=300):
    if base_url not in ("http://127.0.0.1:8014", "http://localhost:8014"):
        raise ValueError("Use the dedicated container verification port 8014")
    with httpx.Client(base_url=base_url, timeout=60) as client:
        health = checked(client.get("/api/v1/health"))
        assert health["db"] == health["redis"] == "ok"
        login = checked(
            client.post(
                "/api/v1/auth/password", json={"email": "broker@helm.demo", "password": "HelmDemo!2026"}
            )
        )
        client.headers["X-CSRF-Token"] = login["csrf"]
        unique = uuid4().hex
        case = checked(
            client.post(
                "/api/v1/demo/requests",
                json={
                    "id": f"container-{unique}",
                    "name": f"Fictional container {unique}",
                    "needs": {
                        "budget_annual_pence": 250000,
                        "coverage": {"cancer": {"level": 3, "must_have": True}, "outpatient": {"level": 2}},
                    },
                },
            )
        )
        case_id = case["id"]
        checked(client.post(f"/api/v1/cases/{case_id}/sign-off", json={"dnr_acknowledged": True}))
        checked(client.post(f"/api/v1/cases/{case_id}/release", json={}))

        def await_state(expected):
            started = time.monotonic()
            deadline = started + timeout_seconds
            while time.monotonic() < deadline:
                # Listing never processes jobs; the separate Arq worker must advance this case.
                listing = checked(client.get("/api/v1/cases", params={"limit": 20, "q": unique}))
                current = next(c for c in listing["items"] if c["id"] == case_id)
                if current["state"] == expected:
                    return round(time.monotonic() - started, 3)
                if current["state"] in ("PAUSED_NEEDS_HUMAN", "UW_REFERRAL"):
                    raise AssertionError(f"Unexpected halt: {current['state']}")
                time.sleep(0.5)
            raise TimeoutError(f"Arq did not advance the case to {expected}")

        review_seconds = await_state("BROKER_REVIEW")
        case = checked(client.get(f"/api/v1/cases/{case_id}"))
        assert len(case["quotes"]["quotes"]) == 30
        selected = [r["plan"]["id"] for r in case["ranking"]["top"][:3]]
        case = checked(
            client.post(
                f"/api/v1/cases/{case_id}/selection",
                json={
                    "ranking_id": case["ranking"]["id"],
                    "selected": selected,
                    "survey": {"thumbs": dict.fromkeys(selected, "up")},
                    "acknowledgements": selected,
                },
            )
        )
        case = checked(
            client.put(
                f"/api/v1/cases/{case_id}/suitability",
                json={
                    "text": case["pack"]["suitability_final"],
                    "dnr_sections_confirmed": [
                        "priorities",
                        "coverage",
                        "budget",
                        "household",
                        "medical_flag",
                    ],
                    "unmet_needs_addressed": [
                        f"{n['plan_id']}:{n['need']}" for n in case["pack"]["unmet_needs"]
                    ],
                },
            )
        )
        proof = checked(client.post("/api/v1/auth/step-up", json={"password": "HelmDemo!2026"}))
        queued = checked(
            client.post(
                f"/api/v1/cases/{case_id}/approve",
                json={"pack_hash": case["pack"]["pack_hash"], "step_up_token": proof["step_up_token"]},
            )
        )
        assert queued["state"] == "AWAIT_APPROVAL" and queued["delivery_pending"]
        publish_seconds = await_state("PUBLISHED")
        final = checked(client.get(f"/api/v1/cases/{case_id}"))
        assert final["publication"]["status"] == "demo_delivered"
        evidence = checked(client.get(f"/api/v1/cases/{case_id}/evidence"))
        assert evidence["audit_chain"]["verified"]
        assert {a["gate"] for a in evidence["approvals"]} >= {"G0", "G1", "G2"}
        link = final["publication"]["magic_link"]
        assert httpx.get(link).status_code == 200
        assert httpx.get(link).status_code == 410
        result = {
            "verified": True,
            "health": health,
            "case_id": case_id,
            "quotes": 30,
            "final_state": final["state"],
            "delivery": final["publication"]["status"],
            "worker_advanced_without_detail_polling": True,
            "audit_chain_verified": True,
            "magic_link_single_use_verified": True,
            "seconds_waiting_for_broker_review": review_seconds,
            "seconds_waiting_for_publication": publish_seconds,
            "functional_timeout_seconds": timeout_seconds,
            "performance_target_verified": False,
            "real_emails_sent": False,
        }
        Path(output).write_text(json.dumps(result, indent=2), encoding="utf8")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8014")
    parser.add_argument("--output", default=".runtime/qa/container-workflow.json")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args()
    verify(args.base_url, args.output, args.timeout_seconds)
