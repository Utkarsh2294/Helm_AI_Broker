# Broker portal pilot handover — unsigned

Date: 30 October 2026. Scope: the complete main plan in `docs/spec/HELM_BROKER_PORTAL_PROJECT_PLAN main.md`.

**Fictional demonstration: available. Real-customer pilot: NO GO until the release gates below have named owners and evidence.** Automated checks do not constitute legal, clinical, security or regulatory approval.

The owner requested a **demo document flow to showcase how this works**. The [Pilot showcase walkthrough](DEMO_SHOWCASE.md) provides the implemented seven-PDF flow, normal G0–G2 journey, independent fictional compliance/legal reviews, and downloadable bound decision record. This demonstration replaces the request for real pilot details for the current task; the live gates below remain unchanged.

## Demonstration walkthrough

1. Start PostgreSQL/Redis and `scripts/start.ps1`; open `http://127.0.0.1:5180`. Alternatively, use the seven-service Compose deployment. Demo identities are listed in the operator guide.
2. Create a fictional request. Review the source facts, priorities, budget and benefit requirements. Make a reasoned edit and wait for its saved version.
3. For ambiguous medical wording, verify identity, reveal the original, and record the broker's review. Generic Resume and G0 cannot bypass an unresolved review.
4. Sign G0, optionally pause release with a reason, then explicitly release G1 to the five fictional partners. Exercise the eight recorded scenarios.
5. Review every shortlisted policy: stars, Recommend/Exclude/Refer and a written reason. Review the criterion explanations, confidence intervals and blockers. Select and order exactly three policies with Recommend decisions.
6. Review the suitability draft, gaps and each selected plan. Save all declarations and unmet-need confirmations. Re-authenticate and approve the bound pack. The worker contacts MockCore only after approval is committed.
7. Export JSON/PDF evidence, inspect its hash chain and historical view. A signed Core event can record link expiry, acceptance, decline, clarification or a fictional binding confirmation. Closure creates an encrypted, redacted PDF.
8. Record a complaint and sign in as its compliance owner to resolve it. Evaluate undisputed feedback; demonstrate separate compliance and lead approvals, shadow results and rollback. Promotion requires 30 labelled cases and at least 0.02 NDCG@3 improvement.

The local model fixture, fictional ToBAs, demo adviser identifiers and MockCore handoff are labelled accordingly. No real insurer, email, paid model call, payment or policy purchase is performed.

## Release gates requiring people or a deployment environment

| Owner | Required evidence | Status |
|---|---|---|
| Compliance lead | Real adviser authorisation, advice/underwriting rules, IPIDs, ToBAs, cancellation/search-basis/remuneration wording, complaints policy and representative outcomes | Unassigned; unsigned |
| Legal/DPO | DPIA, lawful/special-category bases, supplier contracts and regions, consent policy, retention period, legal holds and a lawful deletion design | Unassigned; unsigned |
| Security owner | Triage unresolved CrewAI/ChromaDB and base-image advisories, deployment-specific authenticated penetration test and accepted medium findings | Unassigned; unsigned |
| Accessibility reviewer | Manual NVDA/VoiceOver and real-device acceptance in addition to automated WCAG checks | Unassigned; unsigned |
| Operations owner | TLS/secure cookies, external secrets/KMS, least-privilege database access, backup-and-key restore, external immutable audit anchors, paging and recovery exercise | Unassigned; unsigned |
| Consumer/Core owner | Real OAuth/webhook contracts, delivery/expiry/revocation and binding acknowledgements, with approved notification channels | Unassigned; unsigned |
| Product/model owner | Representative extraction/OCR, fairness and outcome evaluation; approved model provider and monitoring if enabled | Unassigned; unsigned |

The six/seven-year retention conflict in the source documents is intentionally a policy-review job rather than automatic destruction of immutable records. Local performance figures are reported with their environment and unmet targets; they are not production capacity claims.

## Evidence and rollback

Use `docs/phases/MAIN_PHASES.md` and `docs/verification/` for executed checks. Earlier phase evidence is retained as historical evidence against the previous specification. The main-plan reports supersede it for current acceptance.

Preserve PostgreSQL/SQLite data and `.runtime/demo.key`, RSA signing keys and Compose key volumes. For code rollback, use an isolated checkout and a database/key backup tested against that version. Do not downgrade a populated evidence schema, rewrite approvals, delete volumes or replace keys as a debugging shortcut. Pause agents and revoke affected sessions during an incident. The model rollback endpoint restores the previous champion without rewriting published advice.

Decision, reviewer names, signatures and approved deployment URL remain blank until supplied by the responsible people. Garv Gupta is the requested commit author, not a fabricated approval signatory.
