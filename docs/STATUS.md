# Current build status

The active specification is [the complete main plan](spec/HELM_BROKER_PORTAL_PROJECT_PLAN%20main.md), supplied on 30 October 2026. See [the main-plan phase ledger](phases/MAIN_PHASES.md) for current acceptance and [the baseline comparison](phases/MAIN_PLAN_BASELINE.md) for the gaps identified against the earlier build.

Main-plan P0–P4 are verified for the local prototype. The latest full backend run passes 506 tests; subsequent focused checks cover the final halt, pause, edit and migration changes. Production web build, lint, Spectral contracts, SQLite/PostgreSQL migrations and immutable SQL quotation evidence pass. Actual HTTP fan-out retrieves thirty quotes from five fictional partners in 1.734 seconds, and retains twenty-four quotes in 6.953 seconds when one partner times out. Broker publication, medical reveal/review, successive fact-find autosaves, G1 pause/resume and three viewport sizes pass browser checks. P5 is in progress. The earlier [phase evidence ledger](phases/EVIDENCE.md) describes the previous specification, whose phase boundaries differ.

The project remains a fictional prototype. The real consumer portal, insurers, paid model providers and email delivery are not connected. Existing records, encryption keys and commit history are preserved. New commits use the latest requested name, Garv Gupta.

Live use remains blocked by unresolved dependency advisories, representative extraction/security acceptance and the named FCA/legal/compliance approvals required in P11. No legal signature or real broker authorisation is implied by automated tests.

Read [the launch checklist](launch-checklist.md), [DPIA draft](dpia/helm_broker_portal_dpia.md), [model card](model-cards/engine-v1.1.md) and [operator guide](runbooks/operator-guide.md) before connecting real data.
