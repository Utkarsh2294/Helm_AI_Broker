# Helm Broker Portal — Policy Buying & Completion Workflow

## ⚠️ DEMO-ONLY SCOPE — READ FIRST

Everything in this document builds a **demo-grade** workflow, not a production one:

- There is **no live connection to the consumer side yet** — consumer actions (accepting the IPID, signing the declaration, submitting the medical questionnaire, confirming bank details) are **simulated** via a stub consumer portal / seeded fixture data, triggered instantly by the broker or a "Simulate consumer response" demo button.
- There is **no waiting period** anywhere in this flow. Where a real insurer might take days, the demo fires the next step immediately (configurable 0–3 second delay purely for visual pacing, using the same `DemoClock` injectable clock used elsewhere in the project).
- There is **no real insurer portal integration**. The final "send to insurer" step calls a mocked `InsurerSubmissionAdapter` that returns a fake policy number instantly. Wiring this to a real insurer API is explicitly out of scope and flagged as a TODO in Section 11.
- All generated documents (IPID, TOBA, Moratorium Declaration, FMU Questionnaire, banking request) are **real in structure and wording** (built from genuine UK regulatory templates — see Section 17 Sources) but are watermarked `DEMO — NOT A REAL POLICY DOCUMENT` in the footer of every PDF so they can never be mistaken for a live document.
- Every phase master prompt below repeats this constraint so it cannot be missed by whoever builds from a single phase in isolation.

---

## 0. Overview & Trigger

This workflow is Phase Group **PB** ("Policy Buying"), and it continues directly from Phase P6 of the main project plan (`HELM_BROKER_PORTAL_PROJECT_PLAN.md`), where the broker publishes the ranked recommendation and a magic link is sent to the consumer.

**Trigger event**: the consumer opens the magic link, reviews the shortlisted/ranked plans, and selects the one specific plan+quote they want to proceed with. That selection is the event that starts everything below.

```
Magic link opened → consumer reviews ranked plans → consumer picks ONE plan
                                                            │
                                                            ▼
                                          case.quote_selected event fires
                                                            │
                                                            ▼
                     Case moves into a NEW top-level dashboard section: "Policy Buying"
                     (separate from the existing case Queue, which only tracks
                      RECEIVED → PUBLISHED cases)
```

### 0.1 Magic-Link Extension — Capturing the Consumer's Choice

The existing magic-link consumer flow (main plan §9.4) is extended with one more screen at the end:

- After the consumer views the ranked plans and any broker commentary, they are asked: **"Which plan would you like to proceed with?"** — a single-select list of the shortlisted plans, each showing premium, insurer, and a "View full recommendation" link back to the explanation (main plan §7).
- Consumer confirms with a **"Proceed with this plan"** button — this is a deliberate, separate confirmation step, not inferred from which plan they scrolled to or clicked on, so the selection is unambiguous and auditable.
- On confirm: `POST /consumer/cases/{id}/select-quote` records `selected_plan_id`, `selected_at`, and the consumer's session fingerprint (for audit), then fires `case.quote_selected`.
- **Demo-mode note**: since there is no live consumer side yet, this screen is replicated as a **broker-triggered demo stub** — a "Simulate: consumer selects plan X" button visible only when `DEMO_MODE=true`, so the whole downstream flow can be demonstrated end-to-end without a real consumer.

---

## 1. New Dashboard Section: "Policy Buying"

A new top-level navigation item, **Policy Buying**, sits alongside the existing Queue, Insights, and Workspace Assistant entry points.

### 1.1 What the section shows

- A list of all cases currently in the Policy Buying pipeline (i.e. past `case.quote_selected`, not yet `CLOSED`), each row showing:
  - Consumer name, selected plan + insurer, current **Policy Buying stage** (one of the 8 stages in Section 13's state machine)
  - A progress bar / stepper mini-widget (IPID → TOBA → Underwriting Declaration → Banking Details → Submitted to Insurer → Policy Issued) so the broker sees where each case sits at a glance
  - "Updates" badge — see 1.2
  - Last activity timestamp
- Clicking a row opens the **Policy Buying case workspace** (Section 4)

### 1.2 "Updates" — what counts as a new update in this section

Each of the following writes an entry to a per-case update feed shown at the top of the case workspace, newest first, and increments the row's Updates badge on the list view:

| Update type | Example text |
|---|---|
| IPID generated | "AI prepared the IPID for review" |
| IPID sent to consumer | "IPID sent to {consumer} for confirmation" |
| Consumer responded to IPID | "{consumer} accepted the IPID with no changes" / "{consumer} requested a change: {summary}" |
| Underwriting declaration sent | "Moratorium Declaration sent for signature" / "Medical Questionnaire sent" |
| Underwriting declaration completed | "{consumer} completed and signed the Medical Questionnaire" |
| Banking details requested | "Banking details request sent to {consumer}" |
| Banking details received | "Banking details received and verified" |
| Submission package ready | "AI has prepared the full submission package — ready for your review" |
| Sent to insurer | "Submission sent to {insurer} (demo)" |
| Policy issued | "Policy number {policy_number} issued" |
| Broker edit | "{broker} edited the {document_type}" |

This feed is the single source of truth for "what's new" — it is what both the Policy Buying list view badge and the Notification Centre (Section 2) read from.

---

## 2. Notification Centre & Priority Queue Integration

This reuses the notification architecture built for the Workspace Assistant (see `HELM_WORKSPACE_ASSISTANT_MASTER_PROMPT` artifact, Section 10) rather than building a second notification pipeline.

- New event types are added to the existing `broker_events` channel: `pb.ipid_ready`, `pb.consumer_responded`, `pb.declaration_completed`, `pb.banking_received`, `pb.submission_ready`, `pb.policy_issued`
- Each fires a notification bell entry + toast exactly like the existing case-state events, with the same click-through-to-case behaviour — except the deep link opens the **Policy Buying case workspace** (Section 4), not the ranking screen
- These cases also get a `priority_score()` contribution (existing deterministic formula, main workspace-assistant plan §10.8): a case sitting in Policy Buying with an **unactioned consumer response** (e.g. consumer requested an IPID change, or submitted the questionnaire and is waiting on broker review) scores as high-priority, same tier as a halted case, because the consumer is actively waiting on the broker
- The existing Task Copilot rail (same plan, §10.2) gets new deterministic task-card types: `review_ipid_response`, `review_declaration`, `review_submission_package` — each with a direct deep link into the exact step of the case workspace that needs the broker's attention

---

## 3. Policy Buying Case Workspace — Digital Client File

This is what the broker sees when they click into a case from the Policy Buying list.

### 3.1 Layout

- **Left panel — Digital Client File**: consumer name, DOB, contact details, the selected plan + insurer + premium, and (critically) the **underwriting type the consumer originally indicated a preference for during fact-find** (`preferredUnderwritingType`, already captured in the main plan's case data — Moratorium or FMU) — this is what Section 5 reads to decide which path to generate
- **Centre panel — Stepper + current step's working area**: the 8-stage stepper from Section 13, with the active stage expanded showing the relevant generated document, the broker action buttons (Review & Send / Approve / Edit), and inline comment/query box
- **Right panel — Update feed** (Section 1.2) and a persistent **"Ask Workspace Assistant about this case"** shortcut (reuses the existing assistant, case-scoped per its own §8.3)
- **Communication thread**: once the first document is sent to the consumer, a running thread view shows every sent document, every consumer response (or, in demo mode, every simulated response), and every broker edit — this is the audit-friendly "conversation" the brief asked for

---

## 4. Cross-Cutting Pattern: Broker Review, Edit & Query Loop

Every phase below (IPID, TOBA, Declaration, Questionnaire, Submission Package) follows the **same interaction pattern**, specified once here and referenced by each phase rather than repeated:

1. AI agent generates a draft of the document from case data
2. Document appears in the centre panel with three actions: **Approve & Send**, **Request AI changes**, **Edit manually**
3. **Request AI changes**: broker types free-text instructions (e.g. "the excess figure is wrong, it should be £250") into a query box; this is sent to the generating agent as a targeted regeneration instruction; the agent produces a new draft version; the old version is kept in the document's version history (never silently overwritten)
4. **Edit manually**: broker edits the rendered document directly (rich-text block editor, same component family as other document views in the portal); saved as a new version, tagged `edited_by_broker: true`
5. Once approved, the document is sent to the consumer (or, in demo mode, simulated as sent) and the step's update feed entry is written
6. When the consumer responds (Section 3.1 communication thread), **the consumer also has edit/query rights on their own side where applicable** — e.g. they can mark the IPID as "all correct" or flag specific lines as needing a change; they do **not** have edit rights on documents that are legally the broker's statement (TOBA, broker's own declarations) — only on their own factual answers (the medical questionnaire, banking details, confirmation of which cover details are correct)
7. Any broker-side edit after a consumer has already responded re-opens that step and re-notifies the consumer, logged clearly in the update feed so there's never ambiguity about which version was actually agreed

This loop is what the brief means by "broker simply writes the changes and the AI processes these changes and prepares the new document" at every sign-off point.

---

## 5. Phase PB-1 — Medical Underwriting Baseline Review & IPID Generation

### 5.1 Objective

Confirm the consumer's underwriting basis (Moratorium vs Full Medical Underwriting / FMU) and generate a UK-standard Insurance Product Information Document (IPID) for the selected plan, clearly stating which underwriting basis applies and what it means for the consumer.

### 5.2 What "establishing the baseline" means in the UI

When a case enters Policy Buying, the first stepper stage shows:

- The underwriting type the consumer indicated during fact-find (Moratorium or FMU), pulled from existing case data — **the broker is shown this, not asked to re-collect it**
- A short, mandatory explainer card the broker must acknowledge before proceeding, generated to the consumer's actual choice, e.g. for Moratorium: *"This consumer has chosen Moratorium underwriting. Under this basis, any medical condition that was present, symptomatic, or treated in the 5 years before the policy starts is automatically excluded until the consumer has gone 2 continuous years without related treatment, medication, or advice. You must make sure the consumer understands this before proceeding, so they don't face a declined claim they didn't see coming."* — for FMU, the equivalent explainer instead states that the consumer will need to disclose their full medical history up front via a questionnaire (Phase PB-4), and that whatever the insurer excludes will be clearly listed as a personal exclusion on the policy, known in advance rather than discovered at claim time.

### 5.3 IPID generation — UK format, standardised structure

The IPID is a **highly standardised, 2–3 page document** under the UK-retained Insurance Distribution Directive template (implemented via ICOBS 6 Annex 3 / the EIOPA IPID template adopted into UK rules). The agent must generate it using the **exact standard section headings and order**, not a freeform summary:

1. **Insurer name and product name** (header band, with insurer logo placeholder)
2. *"What is this type of insurance?"* — one or two sentences identifying the product type (e.g. private medical insurance) and its general purpose
3. *"What is insured?"* — bullet list of what's covered, drawn directly from the plan's `coverage` object (cancer, mental health, outpatient, hospital list level, etc.) in plain language, with the sum insured / benefit limits per item
4. *"What is not insured?"* — standard exclusions for this insurer/plan (pre-existing conditions under the stated underwriting basis, chronic condition management, cosmetic treatment, etc.) — this is the section where the Moratorium/FMU choice is explicitly named again, e.g. *"Any condition excluded under your Moratorium underwriting terms (see your Underwriting Declaration)"*
5. *"Are there any restrictions on cover?"* — excess, waiting periods, network restrictions (`preferredHospitalShare`), referral requirements
6. *"Where am I covered?"* — geographic scope (UK-only, UK + worldwide emergency, etc.)
7. *"What are my obligations?"* — duty of fair presentation, duty to disclose changes, duty to pay premium on time
8. *"When and how do I pay?"* — payment frequency and method, drawn from the plan's premium data
9. *"When does the cover start and end?"* — policy term dates
10. *"How do I cancel the contract?"* — the 14-day ICOBS 7.1 cancellation / cooling-off right, stated verbatim per regulation

The document must stay within the **2-page target (3 pages maximum for complex multi-benefit products)** mandated by the standard — the agent enforces this with a length check and trims explanatory prose (never trims required factual content) if the draft overruns.

### 5.4 Flow

1. Broker opens the IPID stage → agent has already pre-generated a draft (triggered automatically when the case entered Policy Buying) using the 10-section structure above, populated from the selected plan's data and the consumer's underwriting basis
2. Broker reviews using the standard review/edit/query loop (Section 4)
3. Broker clicks **Approve & Send** → IPID sent to consumer (simulated in demo mode) → update feed entry written → case enters "Awaiting IPID confirmation"
4. Consumer response (simulated): either **"All correct, no changes"** or **"I'd like to flag a change"** with free text — both routes handled by the same edit/query loop (Section 4), with the agent regenerating as needed
5. Once confirmed with no outstanding changes, the case automatically advances to Phase PB-2 (TOBA)

---

## 6. Phase PB-2 — Terms of Business Agreement (TOBA)

### 6.1 Objective

Give the consumer the broker's formal Terms of Business — who the broker is, what service they provide, how they're paid, and how to complain — as required before/alongside finalising the sale.

### 6.2 Standard UK TOBA content the agent must generate

Based on standard UK intermediary TOBA structure, the generated document covers:

- **Who we are**: firm legal name, FCA Firm Reference Number (FRN), confirmation of FCA authorisation and permitted activities (insurance distribution)
- **Our service**: whether this is an advised sale (per main plan §6 C1 — Helm is fully-advised in v1), the scope of the market searched (panel of insurers, per IDD Art. 20 fair-analysis requirement — main plan §6 C9), and that recommendations are personalised to the consumer's stated needs
- **How we are paid**: commission/remuneration basis disclosure, consistent with current ICOBS requirements pending the CP26/22 consultation outcome (main plan §6 C11) — **commission-blind language only, never referencing the actual commission percentage used internally by the engine**, since the recommendation itself is commission-blind by design (main plan engine rule E8)
- **Client money**: explicit statement that Helm does not hold client money (CASS 5 — main plan §6 C8); premium is paid directly to the insurer
- **Complaints**: how to complain (contact point, internal timeline), and the statutory right to refer unresolved complaints to the Financial Ombudsman Service after 8 weeks (DISP 8-week clock — main plan §6 C7), with FOS contact details
- **Cancellation & duration**: how the consumer can end the relationship with the broker at any time, and that this TOBA remains in force for the duration of the policy unless replaced
- **Data protection**: brief UK GDPR statement, link to full privacy policy

### 6.3 Flow

Same review/edit/query loop as Section 4. TOBA is typically sent together with, or immediately after, the IPID confirmation — the agent batches them into one consumer-facing message where the demo allows, but keeps them as two logically separate documents with two separate confirmations, since TOBA is a standing agreement and the IPID is product-specific.

---

## 7. Phase PB-3 — Underwriting Declaration (Moratorium Statement or FMU Questionnaire)

### 7.1 Objective

Record the consumer's **fresh, explicit** underwriting responses for this policy. The agent must never infer or copy medical answers from prior notes — every answer here is newly and explicitly given by the consumer for this specific policy.

### 7.2 Branch A — Moratorium Declaration

If the consumer's underwriting basis is Moratorium, the agent generates a short **Moratorium Declaration Statement** (not a full medical history) for digital signature, using this exact wording as the core statement:

> "I understand that any medical condition present, symptomatic, or treated in the last 5 years will be excluded from cover until I have been completely free of treatment, medication, and advice for that condition for a continuous period of 2 full years after the policy starts."

The generated document wraps this statement with: the policy/plan reference, the consumer's name and date, a clear "I accept" digital signature action, and a plain-language restatement of what happens if they later make a claim related to a condition that falls inside this exclusion window (links back to the explainer from Section 5.2 so the messaging is consistent end-to-end).

### 7.3 Branch B — Full Medical Underwriting (FMU) Questionnaire

If the consumer's underwriting basis is FMU, the agent generates a **comprehensive Medical Questionnaire** (sent together with the IPID at the same stage, per the brief) covering, per standard UK FMU practice:

- Personal details and GP name/practice
- Height, weight, smoking and alcohol status
- For each condition, symptom, surgery, or prescription in the **last 5–10 years** (the agent defaults to 5 years for the demo and notes that the real window is insurer-rule-book-specific): date/period, description, treatment received, current status (ongoing / resolved), medication, and any hospital admissions
- Family medical history questions where the specific insurer's rule book requires them (flagged as insurer-dependent, included as an optional section)
- A consent statement authorising the insurer to request further information from the consumer's GP if needed
- Final declaration: "I confirm the above information is complete and accurate to the best of my knowledge"

**Medical data firewall note**: per the main plan's MF1–MF10 rules, the LLM agent **never infers, summarises, or interprets** the consumer's actual medical answers — it only generates the *blank questionnaire structure* and, after the consumer fills it in (simulated in demo mode with seeded fixture answers), passes the raw completed answers through untouched to the broker review screen and ultimately to the insurer. No LLM call ever reads the content of a completed medical answer to draft commentary about it.

### 7.4 Flow

1. Agent generates the Moratorium Declaration or FMU Questionnaire (per branch above) immediately alongside the IPID at Phase PB-1, or as its own stepper stage directly after TOBA — **implementation choice**: for the demo, generate both together with the IPID stage so the broker sees the full underwriting picture in one review pass, but keep them as two separately-tracked documents in the stepper
2. Broker reviews via the standard loop (Section 4), sends to consumer
3. **Moratorium branch**: consumer signs/accepts → done, advance
4. **FMU branch**: consumer completes the full questionnaire (simulated with seeded demo answers) → questionnaire returns to the broker for final sign-off (the brief is explicit that broker does the final sign-off here too, same as every other step) → broker approves → advance
5. On broker approval of either branch, the case's underwriting step is marked complete and the next update feed entry is written

---

## 8. Phase PB-4 — Banking Details Collection

### 8.1 Objective

Once the consumer has accepted the underwriting basis and (for FMU) returned the completed questionnaire, the agent requests the consumer's banking details needed for premium collection, exactly as the brief specifies this as a new step triggered by underwriting acceptance.

### 8.2 Flow

1. Triggered automatically the moment Phase PB-3 is marked complete
2. Agent generates a **Banking Details Request** — a short, clearly-labelled form asking for: account holder name, sort code, account number, payment frequency confirmation (monthly / annual, matching the IPID's payment section), and a Direct Debit mandate consent statement
3. Sent to consumer (simulated in demo mode with seeded dummy banking fixture data — **never real account data in a demo environment**)
4. On consumer response, the agent prepares a **Banking Statement Information summary** — a clean, insurer-ready summary of the payment details (not the raw sensitive numbers, which are stored encrypted per the main plan's AES-256-GCM pgcrypto encryption rules, main plan §11) for inclusion in the final submission package
5. Update feed entry written; case advances to Phase PB-5

**Security note**: bank account numbers are PII/financial data — encrypted at rest, masked in every UI view except the final one-time broker verification screen (showing only last 4 digits elsewhere), and never passed to any LLM call. This mirrors the medical-data firewall pattern but for financial data.

---

## 9. Phase PB-5 — Final Submission Package & Insurer Handoff (Demo Stub)

### 9.1 Objective

Compile everything collected so far into the exact package an insurer needs, and give the broker one simple action to send it — while keeping the actual insurer-side transmission as a clearly-flagged stub for this demo.

### 9.2 What the agent compiles

The agent assembles the **Final Submission Package**, listing everything that needs to go to the insurer:

- Confirmed IPID (final accepted version)
- Signed TOBA acknowledgement
- Completed Underwriting Declaration (Moratorium statement or FMU questionnaire, final accepted version)
- Banking/payment setup summary
- Consumer identity and contact details from the original case record
- A cover note generated by the agent summarising the case for the insurer's new-business team

### 9.3 Broker action

A single prominent action: **"AI has prepared everything to send to {insurer} — Review & Send"**. Clicking it opens a read-only preview of the full package (broker can still drop back into any individual document's edit/query loop from here if something looks wrong) with one final **Send** button.

### 9.4 Demo stub — `InsurerSubmissionAdapter`

```python
class InsurerSubmissionAdapter:
    """DEMO STUB — replace with a real insurer API/portal integration post-demo.
    Returns instantly; no real insurer is contacted."""
    async def submit(self, package: SubmissionPackage) -> SubmissionResult:
        policy_number = f"DEMO-{package.insurer_code}-{random_digits(8)}"
        return SubmissionResult(
            status="issued",
            policy_number=policy_number,
            issued_at=demo_clock.now(),
        )
```

This is explicitly called out as a **TODO for real insurer integration** — the brief itself says "which is not the work right now, just end it there."

---

## 10. Phase PB-6 — Policy Number Generation & Case Closure

### 10.1 Flow

1. `InsurerSubmissionAdapter.submit()` returns instantly in demo mode (Section 9.4) with a generated policy number
2. The agent immediately sends the policy confirmation to the consumer by email, including the policy number, a copy of the final accepted IPID, and a welcome message — sent with **no artificial delay**, per the brief's instruction that the demo should be fast
3. The case's update feed gets a final entry: *"Policy number {policy_number} issued — case complete"*
4. The case moves out of the Policy Buying list and into **Closed Cases**, and is **green-flagged** (a visual success indicator — green badge/border) to distinguish a successfully completed sale from a case closed for any other reason (declined, withdrawn, etc., which use different flag colours per the existing case-state conventions in the main plan)

---

## 11. State Machine Extension

Eight stages, each mapping to a stepper step in the case workspace (Section 3):

| # | Stage | Enters when | Exits when |
|---|---|---|---|
| 1 | `QUOTE_SELECTED` | Consumer picks a plan via magic link (or demo stub) | Case appears in Policy Buying list |
| 2 | `IPID_DRAFTING` | Case enters Policy Buying | Broker approves IPID draft |
| 3 | `AWAITING_IPID_CONFIRMATION` | IPID sent to consumer | Consumer confirms / all queries resolved |
| 4 | `UNDERWRITING_IN_PROGRESS` | IPID confirmed | Moratorium signed OR FMU questionnaire broker-approved |
| 5 | `AWAITING_BANKING_DETAILS` | Underwriting complete | Banking details received & summarised |
| 6 | `SUBMISSION_PACKAGE_READY` | Banking details confirmed | Broker clicks Send |
| 7 | `SUBMITTED_TO_INSURER` | Broker sends (demo stub fires) | `InsurerSubmissionAdapter` returns |
| 8 | `POLICY_ISSUED` → `CLOSED` (green-flagged) | Policy number generated | Terminal state |

This extends, rather than replaces, the 17-state case machine from the main plan — `PUBLISHED` (main plan state 16) is the hand-off point into stage 1 above.

---

## 12. Database Schema

```sql
CREATE TABLE policy_buying_cases (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id             UUID NOT NULL REFERENCES cases(id),
    selected_plan_id    TEXT NOT NULL,
    underwriting_basis  TEXT NOT NULL CHECK (underwriting_basis IN ('moratorium','fmu')),
    stage               TEXT NOT NULL DEFAULT 'QUOTE_SELECTED',
    created_at          TIMESTAMPTZ DEFAULT now(),
    closed_at           TIMESTAMPTZ
);

CREATE TABLE pb_documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pb_case_id      UUID NOT NULL REFERENCES policy_buying_cases(id),
    doc_type        TEXT NOT NULL,   -- 'ipid' | 'toba' | 'moratorium_declaration' | 'fmu_questionnaire' | 'banking_summary' | 'submission_package'
    version         INT NOT NULL DEFAULT 1,
    content         JSONB NOT NULL,
    edited_by_broker BOOLEAN DEFAULT false,
    status          TEXT NOT NULL DEFAULT 'draft',  -- draft | sent | confirmed | change_requested
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE pb_update_feed (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pb_case_id  UUID NOT NULL REFERENCES policy_buying_cases(id),
    update_type TEXT NOT NULL,
    text        TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE pb_banking_details (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pb_case_id      UUID NOT NULL REFERENCES policy_buying_cases(id),
    account_holder  TEXT NOT NULL,
    sort_code_enc   BYTEA NOT NULL,   -- pgcrypto AES-256-GCM
    account_num_enc BYTEA NOT NULL,
    payment_frequency TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT now()
);
```

---

## 13. Master Prompts — Paste-Ready, One Per Phase

Every prompt below repeats the demo-only constraint on purpose — do not remove it even if building phases individually.

### 13.1 Master Prompt — Phase PB-0: Dashboard Section, Notifications, Digital Client File

```
ROLE: Implement the "Policy Buying" dashboard section for the Helm broker portal.
This is DEMO-ONLY: no live consumer-side connection exists yet, so every consumer
action in this phase group is triggered via a broker-facing "Simulate consumer
response" control when DEMO_MODE=true. There is no artificial waiting — demo
actions resolve instantly (0–3s pacing delay only, via the existing DemoClock).

CONSTRAINTS: React 18 + Vite + JSX only (no TypeScript). Python 3.12 + FastAPI
backend. Reuse the existing notification/SSE/Task-Copilot infrastructure built
for the Workspace Assistant — do not build a second notification pipeline.

BUILD:
1. New nav item "Policy Buying" + list view per Section 1.1 of the plan
   (consumer, selected plan, stage stepper mini-widget, Updates badge, last
   activity).
2. pb_update_feed table + write helper, covering every update type in the
   table in Section 1.2.
3. New broker_events types (pb.ipid_ready, pb.consumer_responded,
   pb.declaration_completed, pb.banking_received, pb.submission_ready,
   pb.policy_issued) wired into the existing notification bell, toast layer,
   and priority_score() function (give an unactioned consumer response the
   same priority weight as a halted case).
4. New Task Copilot card types: review_ipid_response, review_declaration,
   review_submission_package, each deep-linking to the right stepper step.
5. The Policy Buying case workspace layout per Section 3.1: left Digital
   Client File panel, centre stepper + working area, right update feed +
   Workspace-Assistant shortcut, and a communication thread view.
6. The magic-link extension from Section 0.1: a final plan-selection screen,
   PLUS its demo-mode stub ("Simulate: consumer selects plan X" button,
   visible only under DEMO_MODE) that fires the same case.quote_selected
   event a real consumer selection would fire.

ACCEPTANCE: a case can be pushed from PUBLISHED into Policy Buying via the
demo stub button, appears correctly in the list and workspace, and a
notification + task card appear for the broker.
```

### 13.2 Master Prompt — Phase PB-1: Underwriting Baseline Review & IPID Generation

```
ROLE: Implement medical underwriting baseline review and UK-standard IPID
generation for the Helm Policy Buying workflow. DEMO-ONLY: generated documents
are structurally and legally accurate but every PDF carries a footer watermark
"DEMO — NOT A REAL POLICY DOCUMENT", and consumer confirmation is simulated
instantly (no real waiting period).

READ FIRST: Section 5 of the Policy Buying plan for the explainer copy and the
exact 10-section IPID structure (insurer/product header, What is this type of
insurance?, What is insured?, What is not insured?, Are there restrictions?,
Where am I covered?, What are my obligations?, When/how do I pay?, When does
cover start/end?, How do I cancel?) drawn from the UK ICOBS 6 Annex 3 / EIOPA
IPID template.

BUILD:
1. On case entry to Policy Buying, auto-display the consumer's existing
   underwriting-basis preference (moratorium|fmu) — never re-ask for it, it
   already exists on the case record.
2. A mandatory explainer card (exact two example strings given in Section 5.2)
   the broker must acknowledge before the IPID step unlocks.
3. An IPID-generation agent that takes the selected plan's coverage/premium/
   excess/network data + underwriting basis and produces the 10-section
   document as structured JSON (not freeform text) so it can be rendered
   consistently and exported to PDF. Enforce the 2-page (3-page max) length
   constraint programmatically — trim explanatory prose, never factual
   content, if the draft overruns.
4. Hook the IPID step into the generic Review/Edit/Query loop (Policy Buying
   plan Section 4): Approve & Send, Request AI changes (free-text →
   regeneration, versioned, old versions kept), Edit manually (rich-text
   block editor, versioned).
5. Consumer-side demo stub: "Simulate: consumer confirms" and "Simulate:
   consumer requests a change" buttons that post into the same endpoint a
   real consumer action would hit.
6. On confirmation with no outstanding changes, auto-advance the case's
   stage to the TOBA step and write the update-feed entries from Section 1.2.

ACCEPTANCE: generating an IPID for a moratorium case and an FMU case produces
two documents that differ only in the "What is not insured?" section's
underwriting-basis wording, both within the length constraint, both
watermarked, both flow correctly through edit/query/confirm.
```

### 13.3 Master Prompt — Phase PB-2: Terms of Business Agreement (TOBA)

```
ROLE: Generate and deliver the Terms of Business Agreement (TOBA) in the Helm
Policy Buying workflow. DEMO-ONLY, same watermarking and instant-simulation
rules as every other phase in this document.

BUILD:
1. A TOBA-generation agent producing the standard UK intermediary TOBA
   sections from Policy Buying plan Section 6.2: who we are (firm name + FCA
   FRN), our service (advised, panel scope per IDD Art.20), how we are paid
   (commission-blind language — never reference the actual commission % used
   internally by the recommendation engine), client money statement (CASS 5,
   no client money held), complaints process (internal route + FOS referral
   after 8 weeks per DISP), cancellation, and a brief UK GDPR data-protection
   note.
2. Same Review/Edit/Query loop as every other document (Policy Buying plan
   Section 4).
3. In the demo, batch TOBA delivery together with the IPID into one
   consumer-facing message, but track them as two separately-versioned
   documents with two separate confirmation states, since TOBA is a standing
   agreement, not product-specific.

ACCEPTANCE: TOBA content never contains an actual commission figure; the
complaints section always states the current DISP 8-week FOS referral right.
```

### 13.4 Master Prompt — Phase PB-3: Underwriting Declaration (Moratorium / FMU)

```
ROLE: Implement the underwriting declaration step — Moratorium Declaration
Statement OR Full Medical Underwriting (FMU) Questionnaire, branched on the
case's underwriting basis. DEMO-ONLY: FMU questionnaire answers are SEEDED
DEMO FIXTURE DATA simulating a consumer's completed answers, never real
medical data; the LLM never reads or summarises completed medical answers
(medical firewall — see constraint below).

HARD CONSTRAINT: this phase touches medical data. Apply the EXACT same MF1–
MF10 medical-data-firewall rules used elsewhere in the project (see the main
project plan Section 12). The agent may generate the BLANK questionnaire
structure and may pass a COMPLETED questionnaire through to broker/insurer
unread, but must NEVER have an LLM call read, summarise, or comment on the
content of a completed medical answer.

BUILD:
1. Branch A (moratorium): generate the Moratorium Declaration Statement using
   EXACTLY this core wording (Policy Buying plan Section 7.2): "I understand
   that any medical condition present, symptomatic, or treated in the last 5
   years will be excluded from cover until I have been completely free of
   treatment, medication, and advice for that condition for a continuous
   period of 2 full years after the policy starts." Wrap it with policy
   reference, consumer name/date, and a digital "I accept" signature action.
2. Branch B (FMU): generate a blank Medical Questionnaire covering personal
   details, GP details, height/weight/smoking/alcohol, and a repeatable
   condition/symptom/surgery/prescription block (date, description,
   treatment, status, medication) for the last 5 years (note in the UI that
   the real window is insurer-rule-book dependent, default 5 years for
   demo), a GP-information-release consent clause, and a final accuracy
   declaration.
3. Both branches go through the standard Review/Edit/Query loop and require
   final BROKER sign-off even after the (simulated) consumer completes their
   side — per the brief, the broker always does final sign-off.
4. Demo-mode consumer completion: a "Simulate: consumer completes
   questionnaire" button that fills in seeded fixture answers and routes
   back to the broker for final approval.

ACCEPTANCE: a moratorium case never shows a medical questionnaire; an FMU
case always does; no LLM call in this phase's trace ever receives a
completed medical answer as input to a generation or summarisation call.
```

### 13.5 Master Prompt — Phase PB-4: Banking Details Collection

```
ROLE: Implement the banking-details-request step, triggered automatically
once the underwriting declaration (Phase PB-3) is broker-approved. DEMO-ONLY:
use seeded dummy banking fixture data for the simulated consumer response —
never collect or display real account data in a demo environment.

BUILD:
1. Auto-trigger on underwriting completion: generate a Banking Details
   Request (account holder name, sort code, account number, payment
   frequency confirmation matching the IPID's payment section, Direct Debit
   mandate consent).
2. Store sort code / account number encrypted at rest (AES-256-GCM via
   pgcrypto, matching the main plan's encryption standard) — mask to last 4
   digits in every UI view except a single one-time broker verification
   screen. Never pass raw account numbers to any LLM call.
3. On (simulated) consumer response, generate a Banking Statement
   Information summary — a clean, insurer-ready payment summary — for
   inclusion in the Phase PB-5 submission package.
4. Demo-mode stub: "Simulate: consumer submits banking details" button using
   seeded dummy data.

ACCEPTANCE: raw account numbers never appear in any LLM prompt/response log
or in more than one UI screen unmasked; the banking summary correctly
reflects the payment frequency already committed to in the IPID.
```

### 13.6 Master Prompt — Phase PB-5 & PB-6: Submission Package, Insurer Handoff Stub, Policy Issuance & Closure

```
ROLE: Implement the final submission package compilation, the demo-stub
insurer handoff, and policy issuance/case closure for the Helm Policy Buying
workflow. DEMO-ONLY: the insurer side is a STUB — InsurerSubmissionAdapter
returns instantly with a generated fake policy number; building a real
insurer API/portal integration is explicitly OUT OF SCOPE here and must be
left as a clearly commented TODO.

BUILD:
1. A submission-package compiler that assembles: final accepted IPID, signed
   TOBA, completed underwriting declaration, banking summary, consumer
   identity/contact details, and an agent-generated cover note summarising
   the case for the insurer.
2. One broker action: "AI has prepared everything to send to {insurer} —
   Review & Send", opening a read-only full-package preview with a final
   Send button. Still allow drop-back into any individual document's
   edit/query loop from this preview if the broker spots an issue.
3. InsurerSubmissionAdapter as a demo stub exactly as specified in Policy
   Buying plan Section 9.4 — synchronous, instant, returns a fake
   DEMO-{insurer_code}-{8 random digits} policy number. Comment it clearly
   as a TODO for real insurer integration.
4. On successful (stub) submission: send the policy confirmation email to
   the consumer immediately (policy number + final IPID + welcome message,
   zero artificial delay), write the final update-feed entry, move the case
   out of Policy Buying into Closed Cases, and apply a GREEN success flag
   distinct from the existing closed/declined/withdrawn flag colours.

ACCEPTANCE: end-to-end, a case can go from "submission package ready" to
"green-flagged in Closed Cases with a visible policy number" in under 5
seconds in demo mode, with every intermediate update-feed entry present and
correctly ordered.
```

---

## 14. Open Questions Carried Over From the Brief

| # | Question | Default taken for this demo plan |
|---|---|---|
| OQ-PB1 | Should TOBA be a one-time acceptance per consumer, or re-confirmed per policy? | Modelled as standing per-consumer, re-shown but not re-signed on repeat business |
| OQ-PB2 | Real insurer submission channel (API vs portal vs email) — unknown per insurer | Stubbed; left as explicit TODO (Section 9.4 / 13.6) |
| OQ-PB3 | FMU questionnaire exact field set varies by insurer rule book | Demo uses a generic 5-year question set; flagged as insurer-dependent |
| OQ-PB4 | Real-world cooling-off / waiting periods that a production system must respect | Intentionally skipped for demo speed — must be reinstated before any non-demo use |

---

## 15. Sources

| Topic | Source |
|---|---|
| IPID standard template & structure | FCA Handbook ICOBS 6 Annex 3 / EIOPA Implementing Technical Standards on the Insurance Product Information Document |
| IPID implementation guidance | Association of British Insurers (ABI) — Insurance Product Information Document Implementation Guide |
| TOBA standard content | Published UK broker TOBA templates (BIBA-aligned templates; Willis, Towergate, Keychoice/RAC, GRP/Ardonagh published TOBAs) |
| Complaints / FOS referral | FCA Handbook DISP 1.6 |
| Moratorium vs FMU underwriting | WeCovr — UK Private Health Insurance Underwriting: Moratorium vs Full Medical Underwriting Explained |
| Client money (no client money held in v1) | FCA Handbook CASS 5 |
| Fair analysis panel requirement | UK Insurance Distribution Directive (IDD) Art. 20 |
