"""Isolated PostgreSQL acceptance benchmark. Creates a fresh helm_qa database.

Never mutates an existing database or seeds synthetic observations into a demo.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))


def main():
    reuse = (
        sys.argv[1].removeprefix("--reuse=")
        if len(sys.argv) > 1 and sys.argv[1].startswith("--reuse=")
        else None
    )
    created = (
        reuse
        or subprocess.check_output(
            [sys.executable, str(ROOT / "tools/create_qa_database.py")], text=True
        ).strip()
    )
    if not created.startswith("helm_qa_") or not created[8:].isdigit():
        raise RuntimeError("Unexpected benchmark database name")
    os.environ.update(
        HELM_DATABASE_URL=f"postgresql+psycopg://helm:helm_local_demo_only@127.0.0.1:55439/{created}",
        HELM_REDIS_URL="redis://127.0.0.1:56389/2",
        HELM_DEMO_BACKGROUND_JOBS="false",
        HELM_AUTH_RATE_LIMIT="500",
        HELM_LLM_ENABLED="false",
    )
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=os.environ,
        check=True,
        capture_output=True,
    )
    from fastapi.testclient import TestClient
    from app.main import app, SessionLocal
    from sqlalchemy import select, text
    from app.db.models import User, SecretJSON, utcnow
    from app.copilot_jobs import refresh_daily_view
    from app.db.store import event_client

    with TestClient(app) as client:
        auth = client.post(
            "/api/v1/auth/password", json={"email": "broker@helm.demo", "password": "HelmDemo!2026"}
        )
        assert auth.status_code == 200, auth.text
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == "broker@helm.demo"))
            user.is_lead_broker = True
            if reuse:
                assert (
                    db.scalar(text("SELECT count(*) FROM case_metrics WHERE case_id LIKE 'bench-%'"))
                    == 100000
                ), "Only a previously seeded benchmark is reusable"
            encoded = SecretJSON().process_bind_param(
                {"name": "Synthetic load fixture", "cover_type": "individual", "postcode": "SW1"}, None
            )
            db.execute(
                text(
                    "INSERT INTO cases (id,core_request_id,state,profile,version,created_at,assigned_to,priority) SELECT 'bench-'||n,'benchmark-'||n,CASE WHEN n%3=0 THEN 'PUBLISHED' ELSE 'BROKER_REVIEW' END,:profile,1,to_char(now()-(n%90)*interval '1 day','YYYY-MM-DD\"T\"HH24:MI:SS.US')||'+00:00',:broker,'normal' FROM generate_series(1,100000) n WHERE NOT :reuse"
                ),
                {"profile": encoded, "broker": user.id, "reuse": bool(reuse)},
            )
            db.execute(
                text(
                    "INSERT INTO case_metrics (case_id,broker_id,coverage_type,state,insurer_id,created_at,closed_at,last_action_at,close_days,budget_pence,csat,body,updated_at) SELECT id,assigned_to,'individual',state,'benchmark-provider',created_at,CASE WHEN state='PUBLISHED' THEN created_at END,created_at,CASE WHEN state='PUBLISHED' THEN 2.0 END,150000,CASE WHEN state='PUBLISHED' THEN 4.0 END,json_build_object('plans',5,'rated',0,'selected_count',3,'coverage',json_build_object('outpatient',3),'must_have',json_build_array('outpatient'),'underwriting','moratorium','state_entered_at',created_at,'state_durations',json_build_object('BROKER_REVIEW',1.5)),created_at FROM cases WHERE id LIKE 'bench-%' AND NOT :reuse"
                ),
                {"reuse": bool(reuse)},
            )
            db.execute(
                text(
                    "INSERT INTO case_provider_metrics (case_id,insurer_id,broker_id,coverage_type,created_at,shown,top_three,selected,accepted,rated_highly,quoted_turnaround,upheld_rate) SELECT case_id,insurer_id,broker_id,coverage_type,created_at,5,3,1,0,0,2,0.02 FROM case_metrics WHERE case_id LIKE 'bench-%' AND NOT :reuse"
                ),
                {"reuse": bool(reuse)},
            )
            db.commit()
            start = time.perf_counter()
            refresh_daily_view(db)
            db.commit()
            refresh_ms = (time.perf_counter() - start) * 1000
        params = "?from=2020-01-01&to=" + utcnow().date().isoformat()
        results = {}
        for endpoint in [
            "volume",
            "aging",
            "time-to-close",
            "satisfaction",
            "insurer-performance",
            "plan-patterns",
            "broker-productivity",
            "overview",
            "cohorts",
            "anomalies",
            "drivers",
            "dashboard",
        ]:
            event_client().incr("helm:insights:epoch")
            latencies = []
            for _ in range(6):
                start = time.perf_counter()
                response = client.get("/api/v1/insights/" + endpoint + params)
                elapsed = (time.perf_counter() - start) * 1000
                assert response.status_code == 200, (endpoint, response.text[:300])
                latencies.append(elapsed)
            results[endpoint] = {
                "cold_ms": round(latencies[0], 2),
                "warm_p95_ms": round(sorted(latencies[1:])[-1], 2),
                "p95_ms": round(sorted(latencies)[-1], 2),
            }
        report = {
            "database": created,
            "rows": 100000,
            "refresh_ms": round(refresh_ms, 2),
            "endpoints": results,
            "limits": {"refresh_ms": 2000, "endpoint_p95_ms": 300},
            "note": "Isolated synthetic numeric operational projections; HTTP in-process ASGI TestClient, real asyncpg/PostgreSQL and Redis. Cold and warm results reported separately.",
        }
        target = ROOT / ".runtime/qa/workspace-benchmark.json"
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
