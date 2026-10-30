# Helm Broker

Independent UK PMI broker workspace. React/JavaScript website, five Python agents,
and an API boundary to the Helm consumer portal. The active specification is the
[complete main plan](docs/spec/HELM_BROKER_PORTAL_PROJECT_PLAN%20main.md); current
acceptance is tracked in the [main-plan phase ledger](docs/phases/MAIN_PHASES.md).

## Run on Windows

Install Python 3.12, [uv](https://docs.astral.sh/uv/) and Node.js 22+. From this checkout:

```powershell
docker compose up -d postgres redis
.\scripts\start.ps1 -Install
```

Open **http://localhost:5180/** (required for browser passkeys). The IP address also supports password/TOTP sign-in. API docs: **http://127.0.0.1:8010/docs**.

- Broker: `broker@helm.demo` / `HelmDemo!2026`
- Assistant (G0 review): `assistant@helm.demo` / `HelmDemo!2026`
- Compliance: `compliance@helm.demo` / `HelmDemo!2026`

Enroll a passkey or TOTP in Security & devices. Demo accounts without MFA may use password re-entry for step-up. All records and
credentials are for a local demo. Stop recorded preview processes with `scripts/stop.ps1`.
Restart without `-Install` to keep the database and existing cases.

`scripts/start.ps1 -CrewAI` runs each step through CrewAI Flows. The default Python
runtime calls the same five tested functions directly and starts faster. Both modes
run grounded code only: **no model credentials, paid calls or consumer medical text
are sent to an LLM**. The framework smoke test exercises all five CrewAI steps.

## Try a complete case

1. Sign in and open a fictional case (or create a new demo request).
2. Review the sourced demands-and-needs record; optionally edit the annual budget.
3. Sign off the fact-find, select a partner scenario, and release the demo RFQ.
4. After about eight seconds, compare the top five, scores, uncertainty and sources.
5. Select three plans in preference order. Acknowledge any blockers and give per-plan feedback.
6. Prepare the pack, review/edit the suitability statement and save all DNR/unmet-need confirmations.
7. Re-enter the demo password and approve. Delivery is simulated and recorded.
8. Export fourteen-section JSON/PDF evidence and replay historical states; run Agent 5's feedback evaluation in Learning & insights.

Pausing survives reloads. Medical clarification and referral scenarios require
explicit demo exception resolution. Complaint holds block agent jobs and cannot be
automatically closed. Repeated imports and repeated partner revisions are deduplicated.

## Five agents

| Agent | Implementation | Output |
|---|---|---|
| 1 Research | `services/api/app/agents/intake.py` | Sourced DNR, missing items, labelled hypotheses, verbatim medical statements |
| 2 Quotations | `services/api/app/agents/quotation.py` | Minimised RFQ, five fictional partners, canonical revision-aware replies |
| 3 Ranking | `services/api/app/agents/ranking.py` | Hard gates, seven utility scores, bounded ROC weights, 1,000 seeded samples, tie and flip analysis |
| 4 Review | `services/api/app/agents/review.py` | Three-plan pack, short survey, unmet needs, commission-deviation flag, approval-bound content hash |
| 5 Learning | `services/api/app/agents/learning.py` | Bradley–Terry proposal, evidence shrinkage, disputed-case exclusion, case-level holdout metrics |

`CaseService` owns persisted state and human approval gates. Agent functions cannot
publish advice. MockCore supplies the consumer boundary in the six-service stack. The real consumer portal and insurer systems are not connected.

## Layout

```
apps/web/                   broker website (JavaScript / JSX)
services/api/app/agents/    intake, quotation, ranking, review, learning
services/api/app/engine/    deterministic recommendation mathematics
services/api/app/db/        database models and migrations
packages/contracts/        shared API contracts
tools/                     demo fixtures and development utilities
docs/                      requirements, architecture and runbooks
```

## Database and worker

The local preview uses SQLite and AES-GCM encrypted snapshots. Alembic applies the
schema and database triggers that reject evidence updates/deletes. Case transitions,
approvals and hash-chained audit events commit together. Pending jobs persist in SQL;
the browser's polling can advance due demo jobs even without Redis.

For PostgreSQL 16 and Redis 7:

```powershell
docker compose up -d postgres redis
# Copy .env.example to .env and select its PostgreSQL/Redis URLs, then:
& "$env:LOCALAPPDATA\HelmBroker\venv\Scripts\python.exe" -m alembic upgrade head
& "$env:LOCALAPPDATA\HelmBroker\venv\Scripts\python.exe" -m arq app.worker.WorkerSettings
```

Set `PYTHONPATH=services/api` when starting the Arq worker from the repository root.
The worker polls durable quotation jobs every five seconds and checks for daily
learning at 02:00 Europe/London (or the next hourly tick after a restart).

`docker compose up --build` runs PostgreSQL, Redis, API, worker, website, MockCore and a standalone fictional partner simulator. Container
ports bind only to loopback. The API and worker share the encryption-key volume.

If Docker Desktop cannot resolve the package hosts, use `scripts/build-containers.ps1`.
It resolves those hosts on Windows for this build and retains package download caches.
For a slow or repeatedly interrupted Docker download, run:

```powershell
.\scripts\build-containers.ps1 -PrepareWheelhouse
docker compose up -d --no-build
```

This downloads compatible Linux wheels through the host network into
`%LOCALAPPDATA%/HelmBroker/linux-wheels`, verifies their SHA-256 hashes against
`uv.lock`, and installs them offline in Docker. Interrupted downloads resume on
the next run. The cache is local and is not committed. TLS and package hash
verification remain enabled. Use `-Wheelhouse <path>` to reuse a completed cache.

**Back up the database and encryption key together.** `.runtime/demo.key` is the
local-only key fallback. Losing or replacing it makes existing encrypted records
unreadable. A live deployment requires KMS-backed key management and access controls.

## Verification

```powershell
$env:UV_PROJECT_ENVIRONMENT = Join-Path $env:LOCALAPPDATA 'HelmBroker\venv'
uv sync --frozen --extra dev --extra agents --link-mode copy
& "$env:LOCALAPPDATA\HelmBroker\venv\Scripts\python.exe" -m ruff check services/api tools
& "$env:LOCALAPPDATA\HelmBroker\venv\Scripts\python.exe" -m pytest -q
& "$env:LOCALAPPDATA\HelmBroker\venv\Scripts\python.exe" -m alembic upgrade head
& "$env:LOCALAPPDATA\HelmBroker\venv\Scripts\python.exe" tools/export_contract.py
```

Start an isolated QA server with `tools/qa-server.ps1` (ports 8012/5182), then run `npm run build` and `npm run test:e2e` from `apps/web`. Use `tools/qa-server.ps1 -Stop` afterwards. QA uses separate fictional records and a separate Redis database; its login limit is raised only for repeated automated sign-ins. Browser tests use installed Microsoft Edge. Set another browser
channel in `playwright.config.js` if Edge is unavailable. Tests cover the full broker
journey, all eight partner scenarios, passkeys, TOTP, search, evidence/replay, contrast and layouts at 1440, 768 and 390 pixels.

GitHub Actions runs backend checks/migrations and the frontend build. The implemented
OpenAPI contract is tracked at `packages/contracts/broker.openapi.json`.

See [docs/STATUS.md](docs/STATUS.md) for exact limits and outstanding live work.

The phase evidence ledger is [docs/phases/EVIDENCE.md](docs/phases/EVIDENCE.md). Operational instructions, the DPIA draft, model card and live launch gates are under `docs/`. Do not treat prototype test results as production approval.
