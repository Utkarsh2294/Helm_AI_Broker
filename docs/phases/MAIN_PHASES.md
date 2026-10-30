# Main-plan acceptance ledger

Specification: `docs/spec/HELM_BROKER_PORTAL_PROJECT_PLAN main.md`. Results below refer to executed checks, not the checkmarks printed inside the supplied plan.

| Phase | Status | Evidence / next work |
|---|---|---|
| P0 Foundations | Complete | 478 backend tests; real two-task mocked Crew and Flow; 3600× clock test; independent app factory; root readiness; valid Core/Broker OpenAPI contracts; seven containers; five standalone partners / thirty quotes; SQLite and PostgreSQL migration round trips and immutable SQL evidence. [Runtime report](../verification/main-plan-p0.json). |
| P1 Design system + authentication | Complete | 488 backend checks; seven frontend unit tests; nine focused browser outcomes, including real WebAuthn and TOTP; five-attempt identity locks; revocable RS256 cookies and separate five-minute step-up; credential changes protected by re-authentication; safe next-route redirects and three signed-out screens. Production build, lint, formatting and migrations pass. |
| P2 Queue + Core + SSE + audit | Complete | 492-test regression plus a malformed-webhook regression; five focused access checks; medical-reveal, complete broker journey and three viewport browser checks. Signed cursor pagination, assigned-case access, scoped audit/insights, one-hour case/session medical grants, deep links and protection against stale polls. PostgreSQL migration/immutability and Spectral checks pass. |
| P3 A1 + DNR | In progress | Existing sourced DNR/firewall; add the revised ambiguity fixtures and editing/crew requirements. |
| P4 A2 + clock | Pending revised acceptance | Existing five-partner/eight-scenario pipeline; verify fan-out and exact clock requirements. |
| P5 Engine + all-plan HITL | Pending revised acceptance | Verify supplied appendices and implement mandatory star/decision/reason reviews for every shortlisted plan. |
| P6 A4 + G2 | Pending revised acceptance | Bind the revised ratings and per-plan confirmations to committed publication. |
| P7 Halts + complaints + referrals | Pending revised acceptance | Complete complaint owner/resolution and halt/referral coverage. |
| P8 A5 + MCR | Pending revised acceptance | Add detailed rating signals and revised shadow/evaluation thresholds. |
| P9 Consumer integration | Pending revised acceptance | Consumer responses, expiry/bind stub and closure evidence. |
| P10 Security + accessibility + performance | Pending revised acceptance | Resolve measured accessibility findings; execute expanded scans and exact load scenarios. |
| P11 Pilot readiness | External sign-off required | Complete software regression/onboarding/runbooks. Actual FCA identity, legal review and compliance sign-off require named humans; no signature will be fabricated. |

P1 adds seven shared-control unit tests and nine focused browser outcomes. The baseline desktop Lighthouse result is Performance 100 / Accessibility 93 / Best Practices 100; accessibility is not presented as passing. Router 7.18.5 replaces the plan's Router 6 pin because the older line has published redirect advisories; the frontend dependency audit is clear after this update. Account locks expire after fifteen minutes; no fictional unlock email is represented as sent. Local signing keys are file-backed; live mode requires a configured private key from an approved secret manager.

The repository uses its existing `services/api/app` package and canonical §5 state names. Conflicting illustrative `helm_api` paths, state aliases and halt labels in phase prompts are reconciled without rewriting historical evidence. UTC audit and security expiry remain unscaled; the demo clock compresses business intervals. PostgreSQL stores application-encrypted sensitive fields and JSONB structured records. Shared PostgreSQL extensions are never dropped by downgrade.
