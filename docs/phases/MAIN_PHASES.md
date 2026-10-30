# Main-plan acceptance ledger

Specification: `docs/spec/HELM_BROKER_PORTAL_PROJECT_PLAN main.md`. Results below refer to executed checks, not the checkmarks printed inside the supplied plan.

| Phase | Status | Evidence / next work |
|---|---|---|
| P0 Foundations | Complete | 478 backend tests; real two-task mocked Crew and Flow; 3600× clock test; independent app factory; root readiness; valid Core/Broker OpenAPI contracts; seven containers; five standalone partners / thirty quotes; SQLite and PostgreSQL migration round trips and immutable SQL evidence. [Runtime report](../verification/main-plan-p0.json). |
| P1 Design system + authentication | In progress | Existing passkeys, TOTP, refresh rotation and step-up; complete the revised route/logout, account-lock and shared-control requirements. |
| P2 Queue + Core + SSE + audit | Pending revised acceptance | Existing queue/replay/hash-chain controls; review ownership, cursor and medical-access policy. |
| P3 A1 + DNR | Pending revised acceptance | Existing sourced DNR/firewall; add the revised ambiguity fixtures and editing/crew requirements. |
| P4 A2 + clock | Pending revised acceptance | Existing five-partner/eight-scenario pipeline; verify fan-out and exact clock requirements. |
| P5 Engine + all-plan HITL | Pending revised acceptance | Verify supplied appendices and implement mandatory star/decision/reason reviews for every shortlisted plan. |
| P6 A4 + G2 | Pending revised acceptance | Bind the revised ratings and per-plan confirmations to committed publication. |
| P7 Halts + complaints + referrals | Pending revised acceptance | Complete complaint owner/resolution and halt/referral coverage. |
| P8 A5 + MCR | Pending revised acceptance | Add detailed rating signals and revised shadow/evaluation thresholds. |
| P9 Consumer integration | Pending revised acceptance | Consumer responses, expiry/bind stub and closure evidence. |
| P10 Security + accessibility + performance | Pending revised acceptance | Resolve measured accessibility findings; execute expanded scans and exact load scenarios. |
| P11 Pilot readiness | External sign-off required | Complete software regression/onboarding/runbooks. Actual FCA identity, legal review and compliance sign-off require named humans; no signature will be fabricated. |

P0 frontend unit-test discovery is configured but currently has no unit files. Existing Playwright checks are separate. P1 will add shared-control unit tests. The baseline desktop Lighthouse result is Performance 100 / Accessibility 93 / Best Practices 100; accessibility is not presented as passing.

The repository uses its existing `services/api/app` package and canonical §5 state names. Conflicting illustrative `helm_api` paths, state aliases and halt labels in phase prompts are reconciled without rewriting historical evidence. UTC audit and security expiry remain unscaled; the demo clock compresses business intervals. PostgreSQL stores application-encrypted sensitive fields and JSONB structured records. Shared PostgreSQL extensions are never dropped by downgrade.
