# Verification record

Built on 29 October 2026 from the three supplied requirement documents. Git commits
are authored and committed as Garv Gupta using his public GitHub noreply identity.

## Automated checks

- Python invariants: input validation, medical-verbatim preservation, release guards,
  insurer simulation, capped normalised weights, deterministic rankings, commission
  neutrality, fixed-anchor scores, hard gates, pack hashing and learning governance.
- Persistence: AES-GCM encryption at rest, hash-chain tamper detection, append-only
  ORM guards, Alembic upgrade and raw-SQL update/delete rejection by database triggers.
- Workflow: fresh human step-up, exact pack hash, role checks, illegal agent gates,
  complaint locks and duplicate import/revision handling.
- CrewAI 1.15.33: all five code-only steps executed with no provider credentials.
- API: unauthenticated access, CSRF, unapproved Origin, input actor injection,
  assistant-role rejection, session logout and idempotent import.
- Browser: complete request → fact-find → RFQ → ranking → three-plan survey →
  suitability edit → fresh approval → evidence download → learning → logout.
- Browser layouts: 1440px desktop, 768px tablet, 390px phone. Screenshots inspected.
  Native case dialogs must stay at the viewport's top and fit its width.
- Vite production build and Ruff checks.

GitHub Actions succeeded for commit `ec1f122`:
https://github.com/Utkarsh2294/Helm_AI_Broker/actions/runs/40879296424
Later commits should be checked against their own run rather than inheriting this result.

## Verification limits

SQLite was exercised locally. Docker Desktop's Linux engine was unavailable, so
PostgreSQL/Redis container execution and the running Arq worker were not validated
locally. Their source/configuration is included. No claim is made about real partner
APIs, real consumer delivery, live model calls, original engine parity, real clinical
suitability or legal approval.

Browser tests used installed Microsoft Edge on Windows. Phone checks use emulated
viewport sizes; physical iOS/Android devices have not been tested.
