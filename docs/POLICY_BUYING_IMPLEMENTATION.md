# Policy Buying implementation checkpoints

Source: [user-supplied workflow](spec/HELM_POLICY_BUYING_WORKFLOW.md), received
4 November 2026. It supplies the requested demo requirements. The user's chat
instruction additionally requires at least 30 commits authored as Garv Gupta,
with an explicit author-verification stop after the first commit is pushed.

## First commit boundary

Checkpoint 1 adds only the eight-stage lifecycle, its ordering tests, this
checklist and an unchanged copy of the supplied specification. It does not yet
add routes, database records or screens. No existing case is migrated or advanced.
Development resumes after the user checks the first commit's identity.

Foundation verification: the 14 new lifecycle checks and three existing clock
checks pass on Python 3.12; Ruff lint and formatting checks pass for the new code.
The copied source specification matches the supplied file's SHA-256 hash.
The full application build and UI acceptance belong to later checkpoints.

## Scope and implementation decisions

- Consumer selection, confirmations, signatures and banking use clearly labelled
  demo controls and fictional fixtures. No real insurer or consumer is contacted.
  Delivery uses a local demo outbox; no external messages are sent by this work.
- Keep local demo generation enabled and external model calls disabled, as the
  user previously requested. Explain deterministic regeneration limits in the UI.
- Reuse existing case permissions, medical access, encrypted snapshots, event
  notifications, SSE, Task Copilot, audit records, PDF tools and injectable clock.
- Keep buying stages in their own record. `PUBLISHED` remains the recommendation
  handoff; confirmed demo issuance closes the original case with a success outcome.
- TOBA is separately versioned and confirmed inside the existing eight stages;
  it does not introduce a ninth stage. Document and questionnaire versions have
  independent confirmations. Neither a UI click nor this lifecycle graph alone
  grants permission or proves document acceptance.
- Consumer responses bind to document versions. Edits invalidate affected
  confirmations and downstream readiness. The transactional service must enforce
  these gates, ownership, demo-only access, concurrency and replay protection.
- Completed medical answers and raw banking details never enter generation,
  assistant context, notification text, audit payloads or general exports.
  Banking storage must use authenticated encryption compatible with the existing
  AES-256-GCM implementation; verify the source's pgcrypto assumption before use.
- Every generated PDF page carries `DEMO — NOT A REAL POLICY DOCUMENT`.
  Check current official guidance before implementing regulatory wording.
  Use fictional firm details, without invented claims of FCA authorisation.
- Preserve the existing light design, per-case audit and original two-decision
  recommendation flow. Buying adds the document approvals explicitly requested
  in this new workflow. Consumer simulation controls remain clearly distinct.

## Thirty meaningful commits

Each checkpoint includes its relevant checks. Split by working capability,
without empty commits or cosmetic changes made solely to increase the count.

| # | Checkpoint | Phase |
|---|---|---|
| 1 | Eight-stage lifecycle, ordering tests, source specification and delivery checklist | Foundation |
| 2 | Buying-case persistence, constraints and migration | PB-0 |
| 3 | Versioned document persistence and immutable history | PB-0 |
| 4 | Append-only update feed and per-broker read position | PB-0 |
| 5 | Published shortlist validation and version-bound selected quote | PB-0 |
| 6 | Authenticated demo consumer selection and idempotent handoff | PB-0 |
| 7 | Scoped buying list and detail endpoints | PB-0 |
| 8 | Policy Buying navigation and pipeline list | PB-0 |
| 9 | Buying workspace, client file and eight-stage stepper | PB-0 |
| 10 | Communication thread, update badges and assistant shortcut | PB-0 |
| 11 | Existing notification/SSE integration and buying deep links | PB-0 |
| 12 | Priority contribution for unactioned consumer responses | PB-0 |
| 13 | Deterministic buying Task Copilot cards | PB-0 |
| 14 | Existing underwriting preference and baseline acknowledgement | PB-1 |
| 15 | Structured ten-section IPID generation and source mapping | PB-1 |
| 16 | Watermarked IPID PDF and measured page-limit checks | PB-1 |
| 17 | Shared broker edit/query loop and version history | PB-1 |
| 18 | Version-bound IPID confirmation and change-request loop | PB-1 |
| 19 | Fictional TOBA generation, independent review and delivery | PB-2 |
| 20 | Standing TOBA acceptance and repeat-consumer handling | PB-2 |
| 21 | Moratorium declaration and simulated signature | PB-3 |
| 22 | Blank FMU questionnaire and insurer-dependent field notes | PB-3 |
| 23 | Encrypted fictional FMU responses and medical-firewall checks | PB-3 |
| 24 | Final underwriting broker approval for both branches | PB-3 |
| 25 | Automatic banking request and fictional response | PB-4 |
| 26 | Encrypted banking, masking and one-time verification | PB-4 |
| 27 | Version-bound submission package and final broker preview | PB-5 |
| 28 | Idempotent demo insurer adapter and instant issuance | PB-5 |
| 29 | Green Closed Cases view and local confirmation outbox | PB-6 |
| 30 | Both-branch browser journeys, regression checks and run guide | Acceptance |

## Acceptance evidence to record during delivery

- Both underwriting branches: published recommendation through selected quote,
  versioned confirmations, broker approvals and green demo closure.
- Role/case permissions, stale versions, duplicate submissions and interrupted
  requests do not bypass approvals or create duplicate policies.
- Raw medical and banking fixtures do not leak through prompts, logs, generic
  exports, feeds or unrelated case access.
- IPIDs meet the measured PDF page limit; every PDF page is watermarked.
- Existing recommendation, priority queue, assistant and Insights paths remain usable.
- Desktop and phone views, keyboard navigation and the instantaneous demo handoff
  are checked; report actual results and remaining limits rather than assume them.
