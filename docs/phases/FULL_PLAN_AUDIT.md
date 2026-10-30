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

## Implemented after the audit

The owner subsequently requested **fictional demonstration documents and review flows** in place of real pilot details. [The executable walkthrough](../DEMO_SHOWCASE.md) records that scope. Thirty-plus substantive follow-up commits implement the gaps below; it does not turn external live acceptance into an automated checkmark.

| Area | Implemented correction | Remaining boundary |
|---|---|---|
| P2/P9 source lifecycle | Signed request revisions invalidate G0/dependent drafts; withdrawals cancel work and durably revoke delivered advice, including during complaint holds; signed messages route possible complaints without replying | Published/closed/complaint-held source updates return a human-review conflict instead of rewriting existing advice |
| P3 documents | Case-scoped, consented and re-authenticated local PDF/text upload, original download, encrypted immutable source evidence, duplicate hashes and explicit scan/transcription errors | No paid OCR/model or inferred fact approval |
| P5 all-NO | Complete current broker assessments, explicit rationale/confirmation, immutable closure evidence and redacted PDF, no publication | Retention is a non-destructive policy-review job |
| P7 referral/operations | Ranking-bound broker referrals and fictional G3 resolution; HTTP simulator recollection; reasoned/versioned priority, lead reassignment and paused-case takeover | Fictional confirmations do not establish insurer acceptance or medical cover |
| P8 governance | Fresh one-use session proof for G5 mutations; proposer independence, 0.02 held-out improvement, separate roles, reasoned rejection/rollback; disputed feedback excluded from shadow labels | Real representative evaluation remains required |
| P8 access/insights | Notebook case scoping and medical redaction; measured outcomes, current rating distributions, complaint clocks, inclusive-IPT summaries and suppressed small cohort slices | No invented age inference, tax liability or live model-quality claim |
| P10 deployment | Built Node web server with fresh script nonces, strict-dynamic, protected errors and non-root web runtime; hash-verified offline Docker bootstrap/dependency cache; latest case snapshots fetched together | Inline React styles remain; strict advisory scans and exact load targets retain their actual failures |
| P10/P11 operations | Create-once local anchor copy/P1 alert and encrypted isolated SQLite restore with every event/snapshot verified | Local files are not external WORM; no production KMS/PITR/paging acceptance |
| P11 demonstration | Seven fingerprinted fictional PDFs, actual G0–G2 case, separate re-authenticated compliance/legal personas and a bound review-record PDF | `live_release_approved` is always false |

The full Python regression passes **560 tests** (including the engine-package tests); the subsequent focused checks also verify returned case priority and showcase reviewer access after assignment. Browser and layout evidence is recorded separately in `docs/verification/`; historical results above are not silently relabelled as a clean final run.
