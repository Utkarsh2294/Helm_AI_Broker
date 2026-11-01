# Workspace assistant acceptance record — 2 November 2026

Source: [Workspace Assistant — Master Prompt](../spec/WORKSPACE_ASSISTANT_MASTER_PROMPT.md).
This record distinguishes implementation from measured acceptance and external configuration.

## Implemented units

| Unit | Implementation |
| --- | --- |
| WA1 assistant | One dock and draggable/phone launcher; keyboard quick-open; contextual prompts; POST SSE local replies; citation popovers; read-aloud controls; browser-held session history; confirmed clearing; fixed capability boundary |
| WA1 documents/voice | Multipart parsing; 25 MB/5-file/50k-per-file/150k-total limits; broker/login/case-scoped SHA cache; preview/page metadata; added formats; browser interim speech and local Whisper/MediaRecorder fallback |
| WA1 evidence | Server-sealed reply receipts; immutable query/response hashes; explicit save-to-case picker; cross-case source checks; supporting research; hide/undo; version-bound draft updates and PDF appendix |
| WA2 schema/event bus | Migrations 012/013; transactional projections and durable notifications; PostgreSQL NOTIFY/LISTEN wake-up; deterministic 50-repeat priority fixture; daily view and worker schedules |
| WA2 notifications/tasks | One stream lease per broker; authenticated replay; scoped inbox/read/read-all; opt-in VAPID push; task cards and snoozes; shared cited explanations; priority banner and queue sorting |
| WA2 Insights | Filtered operational aggregates and view; scoped caches; KPI/volume/aging/state/provider/satisfaction/preference/renewal displays; senior-only productivity; driver/anomaly jobs; scorecard exports and local summaries |

SQLAlchemy async sessions use asyncpg for the new operational routes and aiosqlite
for local tests. The existing atomic case service and transaction hooks are shared
through SQLAlchemy's greenlet bridge. PostgreSQL analytics use aggregate SQL for
spreadsheet-like patterns, state timing and anomalies; they do not decrypt case files.

## Verified checks

- Full backend and ranking-engine regression: **586 passed**, 66 dependency warnings.
- Follow-up changed-feature suite: **19 passed** (assistant/evidence/audio,
  broker scope, notifications, signed satisfaction, migrations and queue filtering).
- Frontend unit tests: **9 passed** across two files.
- Production Vite build and ESLint checks passed during implementation.
- A real 4.08-second Windows-generated voice recording was transcribed locally as
  “Summarize my workspace and show the cases needing review.” CPU `base.en`
  completed the first-load smoke check in 8.27 seconds. No hosted model was used.
- The benchmark creates a separate PostgreSQL database with 100,000 synthetic
  operational rows. The first daily-view refresh measured **1,166.13 ms**.
  Measurements under concurrent builds/tests were slower. Endpoint latency
  acceptance must be evaluated separately; do not infer it from the refresh result.

- Final database-pool/SQL/evidence regression: **10 passed**. Local preview
  maintenance/driver scheduling and idempotency: **1 passed**.
- Browser workflows: **5 passed across the final runs** (two assistant flows;
  complete two-decision journey; background agent progression; task/inbox/Insights
  navigation). Desktop and 390-pixel mobile axe checks in these flows reported
  no WCAG A/AA violations. This is automated coverage, not a manual-device audit.
- Earlier browser failures exposed history initialization, overlapping sticky
  controls and a hidden assistant launcher that closed the task rail. The controls
  and launcher were corrected; the complete workflow rerun passed.
- Docker dependency build completed with cached, hash-verified Linux artifacts,
  including the source-only http-ece dependency. The final source image reuses that
  verified base. API/worker/web images built, and the API became healthy. Local
  Whisper weights were copied into the shared runtime; its capability check is true.

## Performance acceptance profile

The final [100,000-row Docker report](workspace-benchmark-100k.json) measured
**892.24 ms** for materialized-view refresh and **38.39–89.55 ms endpoint p95**.
The defined cache/retrieval smoke profile therefore passes the two-second refresh
and 300 ms p95 thresholds. It uses the deployed Docker internal database/Redis
network and real asyncpg sessions. Each endpoint includes one cache-cold request
and twenty warm requests; p95 is the nearest rank across all 21 observations.

This is not a multi-user production load simulation. Cache-cold requests remain
slower (the full dashboard took 9.2 seconds for this 100,000-case fixture), and
arbitrary filter mixes or concurrent writers may change cache hit rates. These
are retained as practical production-tuning limits. The earlier
[Windows host-to-Docker measurements](workspace-benchmark-host-100k.json) missed
the latency threshold under concurrent builds/tests and are preserved for comparison.

## Deliberate configuration and acceptance limits

- **External LLM replies are off by the broker's explicit choice.** Responses,
  task explanations and summaries are deterministic saved-record demo replies.
  SSE streams those local answers; it is not provider token generation.
- Browser/device microphone, TTS and push permission/provider delivery require
  acceptance on the actual devices. No notification permissions were silently
  requested, no reviewer links were sent, and no external model key was configured.
- Browser speech may use its vendor service; local Whisper is the server fallback.
  Public weights are prepared out of band. Uploaded audio is not retained.
- A generic push reminder is the only outbound payload. No real recipient device
  was enrolled by these checks. Transient provider failures remain retryable.
- Consumer satisfaction/renewal outcomes require signed source events. Missing
  outcomes remain unavailable. A manually entered satisfaction reference is labelled
  unverified; there is no invented market benchmark.
- Hiding research changes the current working recommendation where unsigned;
  immutable audit/evidence and previously signed pack versions remain intact.
- Light mode remains the product preference. The attached prompt's illustrative
  dark-mode clause and older library versions do not override the established app.
- The operational demo is not a live broker pilot authorization. The existing
  source plan's real integration/reviewer requirements remain outside this update.
