# Main plan baseline — 30 October 2026

The active build specification is [the complete main plan](../spec/HELM_BROKER_PORTAL_PROJECT_PLAN%20main.md). The previous specification and its evidence ledger remain historical records. Phase numbers in those documents do not describe the revised plan's phase boundaries.

## Verified before further changes

- Web production build passed. The bundle is 173 KB compressed.
- Backend: 468 tests passed; four focused API/CrewAI checks passed after runtime startup changes.
- Six-service Docker build and execution passed. An independent Arq worker collected 30 fictional quotes and completed G0/G1/G2 publication through MockCore. Audit verification and one-use magic-link rejection passed.
- Sixteen broad browser checks passed earlier; eight focused final checks passed for the complete broker journey, pagination, assistant permissions, keyboard use, three viewport sizes and light-theme readability.
- A real local OTLP/protobuf receiver verified agent spans without the synthetic medical canary or applicant name.
- Desktop Lighthouse on the authenticated queue: Performance 100, Accessibility 93, Best Practices 100. Accessibility requires further work.
- Dependency scanning still reports optional ChromaDB advisories. Live deployment is blocked; the security workflow deliberately reports them.

## Work required by the revised plan

| Phase | Existing foundation | Work to verify or complete against the main plan |
|---|---|---|
| P0 | Repository, PostgreSQL/Redis, API/engine coverage across 468 tests, six containers, Core contract, CrewAI Flows and persisted human feedback | Workspace tooling, application factory, injectable clock, mocked Crew spike, standalone partner simulator and contract lint |
| P1 | Real passkeys, TOTP, rotating sessions, step-up, light design system | Explicit routes/logout variants, complete shared controls, account lock policy and signed access tokens |
| P2 | Queue, pagination, search, SSE replay/pubsub, hash chains | Case access policy, cursor contract, persisted gate-violation evidence and re-authenticated medical access |
| P3 | Sourced structured DNR, document parsing, curated KB, redaction/provider controls | Medical ambiguity fixture/routing, fuller DNR editing and mocked Crew substeps |
| P4 | Five fictional partners, thirty plans, eight scenarios, durable timers/chasers | Clock integration, partner fan-out and explicit insufficient-quote coverage |
| P5 | Deterministic scoring, caps, uncertainty, tie/blocker overlays and prior independent oracle | Run the newly supplied appendices, standalone engine package, criterion explanations, all-plan star/decision/reason reviews and server enforcement |
| P6 | Pack validation, suitability review, fresh one-use G2, committed publication outbox | Bind every shortlisted rating and per-plan suitability confirmation to publication |
| P7 | Halt/resume, referral exception, complaint hold, replay and PDF evidence | Complaint owner/resolution UI, complete halt-resolution coverage and referral records |
| P8 | Bounded Bradley–Terry proposals, held-out evaluation, independent G5, shadow and rollback | Incorporate detailed ratings, thirty-case shadow evidence and the revised improvement threshold |
| P9 | MockCore publication, hashed one-use links | Consumer response/bind stub, expiry notifications and closure records |
| P10 | Headers, red-team checks, DPIA draft, dependency reports, measured load | Accessibility findings, expanded security/contract checks and exact revised load scenarios |
| P11 | Operator guide, model card, launch checklist | Full revised regression, demo onboarding and reviewable go/no-go package; real FCA/legal/compliance sign-off requires named humans |

## Interpretation of conflicting examples

The plan contains different state names, halt-code meanings, endpoint examples and retention periods in different sections. The canonical state graph in §5 and the versioned Core contract in §4.4 take precedence over illustrative snippets. Existing immutable records will remain readable. Compatibility routes may be added rather than destructively renaming stored states.

The user's light-background preference remains in effect. Fictional providers and accounts remain explicit. No insurer emails, paid model calls, real onboarding messages or legal signatures are fabricated. Business-time compression must not shorten security-token lifetimes or alter UTC audit evidence. The retained seven-year evidence policy is a draft requiring compliance confirmation; conflicting six-year wording will not be presented as established law.

The new requested commit author is **Garv Gupta**. Existing history, including earlier commits by Utkarsh Raj, is preserved.
