"""Repeatable local measurements. Mutates only an explicitly selected fictional QA server."""

import argparse
import asyncio
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
import httpx


def summary(values):
    ordered = sorted(values)
    return {
        "samples": len(ordered),
        "p50_ms": round(ordered[len(ordered) // 2], 2),
        "p95_ms": round(ordered[math.ceil(0.95 * len(ordered)) - 1], 2),
        "max_ms": round(ordered[-1], 2),
    }


async def measure(base_url, output, fixture_cases):
    if not base_url.startswith(("http://localhost:8012", "http://127.0.0.1:8012")):
        raise ValueError("Use the dedicated QA server on port 8012; this script creates fictional records")
    async with httpx.AsyncClient(
        base_url=base_url, timeout=60, limits=httpx.Limits(max_connections=100, max_keepalive_connections=100)
    ) as client:
        auth = await client.post(
            "/api/v1/auth/password", json={"email": "broker@helm.demo", "password": "HelmDemo!2026"}
        )
        auth.raise_for_status()
        client.headers["X-CSRF-Token"] = auth.json()["csrf"]
        existing = (await client.get("/api/v1/cases")).json()
        run_id = str(time.time_ns())
        semaphore = asyncio.Semaphore(8)

        async def create(number, unique=False):
            async with semaphore:
                response = await client.post(
                    "/api/v1/demo/requests",
                    json={
                        "id": f"perf-{number}-{run_id}" if unique else f"perf-{number}",
                        "name": f"Fictional performance {number:04d}",
                        "needs": {"coverage": {"cancer": {"level": 3, "must_have": True}}},
                    },
                )
                response.raise_for_status()
                return response.json()

        needed = max(0, fixture_cases - len(existing))
        await asyncio.gather(*(create(i) for i in range(needed)))
        first = await create(100000, True)
        case_id = first["id"]

        async def timed_get(path):
            start = time.perf_counter()
            response = await client.get(path)
            response.raise_for_status()
            return (time.perf_counter() - start) * 1000

        list_times = await asyncio.gather(*(timed_get("/api/v1/cases?limit=50") for _ in range(50)))
        insight_times = [await timed_get("/api/v1/insights") for _ in range(10)]
        ready, readers_ready, sent = asyncio.Event(), 0, None
        connection_times = []

        async def read_event():
            nonlocal readers_ready
            start = time.perf_counter()
            async with client.stream(
                "GET", f"/api/v1/cases/{case_id}/stream?after={first['events'][-1]['seq']}"
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith(":"):
                        connection_times.append((time.perf_counter() - start) * 1000)
                        readers_ready += 1
                        if readers_ready == 50:
                            ready.set()
                    if line.startswith("data:") and json.loads(line[5:])["type"] == "case_assigned":
                        return (time.perf_counter() - sent) * 1000

        tasks = [asyncio.create_task(read_event()) for _ in range(50)]
        await asyncio.wait_for(ready.wait(), 45)
        sent = time.perf_counter()
        assigned = await client.post(f"/api/v1/cases/{case_id}/assign", json={})
        assigned.raise_for_status()
        delivery_times = await asyncio.wait_for(asyncio.gather(*tasks), 45)
        rank_cases = await asyncio.gather(*(create(200000 + i, True) for i in range(20)))
        for case in rank_cases:
            response = await client.post(
                f"/api/v1/cases/{case['id']}/sign-off", json={"dnr_acknowledged": True}
            )
            response.raise_for_status()
            response = await client.post(f"/api/v1/cases/{case['id']}/release", json={})
            response.raise_for_status()
        for case in rank_cases:
            for _ in range(60):
                response = await client.get(f"/api/v1/cases/{case['id']}")
                response.raise_for_status()
                if response.json()["state"] == "BROKER_REVIEW":
                    break
                await asyncio.sleep(0.2)
            else:
                raise RuntimeError("Ranking fixture did not reach broker review")

        async def enqueue(case):
            start = time.perf_counter()
            response = await client.post(f"/api/v1/cases/{case['id']}/ranking", json={})
            if response.status_code != 202:
                raise RuntimeError(response.text)
            return (time.perf_counter() - start) * 1000

        enqueue_times = await asyncio.gather(*(enqueue(case) for case in rank_cases))
        result = {
            "measured_at": datetime.now(timezone.utc).isoformat(),
            "server": base_url,
            "environment": f"Local Windows, {(await client.get('/api/v1/health')).json().get('db_backend', 'database')}, Redis DB 1; not a production capacity claim",
            "case_count": (await client.get("/api/v1/insights")).json()["cases"],
            "case_list_50_concurrent": summary(list_times),
            "insights": summary(insight_times),
            "sse_50_connections": summary(connection_times),
            "sse_event_delivery": summary(delivery_times),
            "ranking_enqueue_20_concurrent": summary(enqueue_times),
        }
        Path(output).write_text(json.dumps(result, indent=2), encoding="utf8")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8012")
    parser.add_argument("--output", default=".runtime/qa/performance.json")
    parser.add_argument("--fixture-cases", type=int, default=1000)
    args = parser.parse_args()
    asyncio.run(measure(args.base_url, args.output, args.fixture_cases))
