# Full-plan conformance audit

Source read in full: `docs/spec/HELM_BROKER_PORTAL_PROJECT_PLAN main.md`, 4,793 lines, SHA-256 `a51db7391ef3a07f3732567197d49eec33b7fec2035bda478579dcc7c48c1685`. This includes sections 0–19 and all three engine appendices. Supplied examples are requirements input, not evidence that their checkmarks passed.

The earlier phase ledger describes working prototype paths. It does not establish completion of every requirement in the main plan. This audit tracks the additional work without replacing historical test evidence.

| Area | Gap found in the implementation | Required correction |
|---|---|---|
| P2/P9 Core lifecycle | Updated/withdrawn request events and consumer-message handling incomplete | Validate signed events, invalidate dependent drafts, stop withdrawn work, route complaints without replying |
| P5 negative path | All-NO decisions cannot close the case | Broker-confirmed closure with complete current assessments, encrypted rationale and audit; no publication |
| P7 referral | Simulator referral can resolve, but broker-originated referral is missing | Versioned referral submission/resolution, plan/ranking binding and role guards |
| P7 case operation | Reassignment, priority and takeover lack complete UI/API paths | Case-scoped operations with optimistic concurrency, explicit reasons and accessible controls |
| P8 governance | G5 mutations lack fresh one-use step-up; rejection and reasoned rollback incomplete | Bind independent decisions to authenticated reviewers and immutable rationale |
| P8 data access | Notebook rows are returned without case ownership filtering | Apply case access and medical redaction to list and review paths |
| P8 insights | Limited aggregate dashboard | Implement measured outcome/rating/complaint/IPT metrics and privacy-safe slices; no fabricated charts |
| P10 performance | Queue/detail and SSE targets not all met | Profile exact scenarios, reduce redundant SQL and synchronous publication work, retain every measured target |
| P10 security | Critical transitive dependency and base-image findings | Verify supported dependency/image fixes; keep strict scans and record unavoidable upstream blockers |
| P10 verification | All conditional case tabs, zoom, manual accessibility and full clean browser run incomplete | Expand automated coverage and record manual evidence separately |
| P10/P11 operations | External audit anchoring, alert delivery, restore/rotation and pilot onboarding incomplete | Implement configurable, tested operational paths and a deployment-bound readiness checklist |
| P11 approval | Actual legal entity, authorised staff, staging integrations and named signatories absent | Obtain owner-supplied details; never create fictional real-world approval evidence |

Decisions already recorded remain applicable: canonical section 5 states and H1–H10 codes; strict medical-data prohibition; current secure package versions; append-only rating versions; no automated G5 promotion; inclusive IPT arithmetic. The conflicting six/seven-year retention examples require an explicit versioned policy decision and legal-hold handling, not deletion chosen by the coding assistant.

Thirty meaningful follow-up commits are requested. Each should represent a reviewable implementation, regression, integration or verification result. Empty commits and splitting unchanged files to inflate the count are excluded.
