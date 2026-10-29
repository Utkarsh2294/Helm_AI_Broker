# Complete-plan baseline · 30 October 2026

Starting revision: 8f9aecf (15 existing commits). This implementation run adds at
least 30 new functional commits authored as Utkarsh Raj; previous attribution stays intact.

Baseline verification: 18 Python tests passed; Ruff passed; Vite production build passed.
Docker Engine 29.6.1 is available. PostgreSQL/Redis verification is now possible.

| Phase | Baseline gap |
|---|---|
| P0 | Standalone Mock Core, complete domain schema, contracts, six-service compose, human-feedback spike |
| P1 | WebAuthn/TOTP, refresh reuse detection, devices, shared tokens/dark mode/motion |
| P2 | Real SSE client, command palette, quick look, pagination and explicit state graph |
| P3 | Medical access controls, gateway redaction/budgets, knowledge base and extraction evaluation |
| P4 | Gateway adapter, all 30 plans, timer/chase/referral and signed webhook ingestion |
| P5 | Expanded engine invariants, commission correlation and independent JS oracle |
| P6 | Grounded dual-audience explanations, copilot and provenance interactions |
| P7 | Complete manifest validation, reviewed unmet needs, external publish acknowledgement |
| P8 | G5 four-eyes, shadow models, notebook and approved playbooks |
| P9 | Historical replay, PDF evidence, insights, audit anchoring and tracing |
| P10 | Expanded red-team suites, headers, shared limits, dependency audit and DPIA |
| P11 | Scripted demo, runbooks, actual performance measurements and launch evidence |

## Reconciliations

- No invented test/Lighthouse/performance results, despite prompts requesting simulated output.
- Market reference bands remain fixed per case/catalogue version. Recomputing from each
  candidate batch conflicts with the explicit no-rank-reversal requirement.
- Monte Carlo explores uncertain preferences; the learned-weight cap applies to deployed
  learning, not to unconstrained Dirichlet samples (the document mixes those concepts).
- Evidence-preserving migrations prohibit destructive rollback on populated evidence.
  Clean development databases may round-trip; existing user data must not be deleted.
- The document gives worked-example scores without the full original plans or JS oracle.
  Independent arithmetic parity is testable; original-example parity is not asserted.
- Clinical, legal, provider-region and real-device sign-offs remain external launch gates.

Each phase records implemented checks and remaining external acceptance separately.
