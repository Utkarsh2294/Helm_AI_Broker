# Build boundary

The three supplied documents describe the intended system; omitted UI, firewall,
phase prompts and engine appendices are not assumed to exist. Implementations are
verified locally rather than inheriting the documents' test claims.

Build order: folder architecture → typed boundaries → A1 → A2 → A3 → A4 → A5 →
database → guarded API → broker website → integration tests and runbook.

Demo data is fictional. Real medical data and external publication remain disabled
until the consumer API contract, medical firewall and launch controls are verified.

## Implemented

- All five independently testable agents, plus optional CrewAI Flows runtime.
- Seeded broker/assistant/compliance identities, Argon2 passwords, hashed session
  tokens, httpOnly cookies, origin/CSRF checks, session expiry and approval step-up.
- Fact-find review/edit/sign-off, partner simulation, comparison, three-plan survey,
  suitability editing, content-bound human approval and simulated publication.
- Seven criteria, hard exclusions/human routing, fixed market reference band,
  per-criterion points, insurer diversity, seeded Monte Carlo, tie and flip analysis.
- Bounded learning proposals with case-level holdout; no automatic activation.
- Encrypted, versioned evidence, audit chain verification/export, persisted jobs,
  pause/resume and complaint holds. SQLite and PostgreSQL SQLAlchemy schema/migration.
- Responsive workspace, login/logout, agent team, partner directory, learning and audit views.
- Arq worker, Docker configuration, API contract export, startup scripts and CI.

## Explicit demo reductions

The persisted UI states collapse the internal intake/ranking/drafting transitions
from the long-form plan. They do not claim the entire P0–P11 acceptance checklist is
complete. This implementation was built in the owner's requested order: all five
agents first, then persistence.

The supplied engine appendices were absent. Mathematics was independently
implemented from Part 3 and invariant-tested; parity with that absent reference is
not asserted. Ranking constants are uncalibrated design defaults. Sampled weight
uncertainty is not a probability of clinical suitability or policy coverage.

The learning module uses a MAP-style L2 prior and evidence shrinkage. A proposed
update records consumed selection IDs; insufficient-evidence runs retain pending
feedback. There is no model activation endpoint. Four-eyes approval, shadow-mode
promotion, fairness reporting and rollback must be implemented before activation.

Authentication uses password re-entry for **demo** step-up, not production MFA.
Passkeys, TOTP, rotating refresh families, recovery, firm onboarding and multi-tenant
isolation are outstanding. The portal is restricted by configuration to demo mode.

CrewAI runs local deterministic steps. LLM crews, OCR, curated-knowledge retrieval,
redaction, region-enforced model routing and medical firewall evaluations await the
remaining specification. No real medical conclusions or clinical inferences exist.

The consumer contract is proposed only. Live OAuth/HMAC webhooks, partner APIs,
FCA checks, real IPIDs, six-hour live deadlines/chasers, late-response reconciliation,
transactional external delivery/retries and consumer magic links remain outstanding.
All partners and document references shown in the demo are fictional.

Evidence uses an app-level AES-GCM key and database immutability triggers. KMS key
rotation, separate least-privilege database roles, write-once daily-root anchoring,
PDF exports, retention jobs and external security review remain launch work.
The current single-firm demo allows authenticated staff to read all demo cases.

The local environment has exercised SQLite. Docker/PostgreSQL/Redis execution is
not claimed unless explicitly recorded in the verification runbook. Real legal and
regulatory assertions from the supplied documents have not been independently certified.
