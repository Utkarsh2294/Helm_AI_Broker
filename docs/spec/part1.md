# HELM BROKER PORTAL — AGENTIC UK PMI BROKER WORKSPACE
## Project plan, architecture, recommendation-engine maths and phase-by-phase master prompts
### Website: React in plain JavaScript (no TypeScript) · Backend / agents / engine: Python (FastAPI + CrewAI) · Separate repo, API-connected to the Helm consumer site

- Version 1.1 · 29 Oct 2026 · Owner: Helm AI
- Companion to: `HELM_AI_UK_TRANSFORMATION_MASTER_PROMPT.md` (consumer site, UK market)
- Product: a **separate** website for licensed brokers. It receives consumers' quote requests from the consumer site's API, runs a five-agent pipeline, and ends with a **human broker approving** a recommendation that reaches the consumer by magic link.

> **Correction applied (v1.1):** v1.0 wrongly limited the *whole stack* to JavaScript. Your rule is: **no TypeScript, and the website itself is normal JavaScript. The backend, agents and recommendation engine are free to use the best tool.** This version uses **Python + FastAPI + CrewAI + PostgreSQL** for everything behind the website.

---

## 0. HOW TO USE THIS FILE

1. Give the **whole file** to any coding LLM. It is self-contained, including the verified recommendation-engine code (Appendix A: Python, Appendix B: tests, Appendix C: the JavaScript oracle it was checked against).
2. Read **Parts 1–4** once (decisions, research, compliance controls, architecture, engine, UI). They are the contract.
3. Run phases **P0 → P11 in order** (Part 5). Each has a paste-able **MASTER PROMPT**. Do not start a phase until the previous phase's acceptance list is green.
4. Prefix every phase prompt with the **GLOBAL MASTER PROMPT** (Section 14).
5. Anything tagged `[VERIFY]` must be confirmed by the owner, a compliance officer or a UK-qualified solicitor before real customers use the system.

### Evidence legend

| Tag | Meaning |
|---|---|
| `[VERIFIED]` | Checked in this session by running code, or by reading the primary source page. |
| `[SOURCED]` | From a web source (often vendor, law-firm or trade press). Reasonable, not primary. |
| `[DESIGN]` | A decision made in this plan. Change it if you disagree; the reason is given. |
| `[VERIFY]` | Likely wrong, changing, or legally consequential. Check before launch. |

### What was actually verified in this session

- **Recommendation engine, JavaScript reference:** 16/16 tests pass (Node v22). The first run found a **real bug**: the "±30% learning cap" was broken by renormalisation (a weight rose +57%). Fixed with a bisection projection; a stronger test now guards it.
- **Recommendation engine, Python production port:** **18/18 tests pass** (Python 3.13): 14 behavioural invariants + 4 **parity tests that reproduce the JavaScript reference on 40 randomly generated cases to 1e-9**, including the seeded Monte-Carlo output, the learning step and the cap. Code in Appendix A.
- **FCA Handbook pages read:** ICOBS 7.1 (cancellation) and ICOBS 5.3 (suitability, record-keeping, personal recommendation).
- **CrewAI documentation read** (`@human_feedback`, Flows, async feedback provider; requires CrewAI ≥ 1.8.0). **The CrewAI package itself was NOT installed or run here**, so Phase 0 includes a short spike to confirm the exact API on the pinned version.
- **Not verified:** any live partner integration, any real FCA Register call, the legal conclusions in Part 1 §3 (design assumptions, not legal advice), and the "Ocean" reference (§2.3).

---

# PART 1 — DECISIONS, RESEARCH, COMPLIANCE

## 1. What we are building (your brief, restated)

- **A completely separate website** for brokers (own repo, own deployment) whose API talks to the consumer site's API. Reason: easier to maintain, faster to ship, not everything in one GitHub.
- **Look and feel:** modern, Apple-style (clarity, depth, spring motion, gestures); it does **not** need the consumer site's colours. **Start with the broker login and logout pages.**
- **Broker sees** which consumers requested quotations and works them through an **agentic workflow**:
  1. **Agent 1** reads all requirements and researches the consumer's needs.
  2. **Agent 2** generates a quotation request, sends it to **all partners**, and waits (about **6 hours** live; in **demo** it completes immediately with partner quotations received).
  3. **Agent 3** uses the **recommendation engine** to rank the **top 5** policies (requirements, documents required, what each offers, consumer needs) with a **detailed score and explanation**.
  4. **Agent 4** shows the human broker the best policies and why. The broker **selects top 3**, gives a **very short survey** (thumbs/number + short note), **approves**, and the recommendation goes to the consumer by **magic link**.
  5. **Agent 5** reads all feedback **daily** and improves the recommendation engine.
- **UK rules** from your notes are built in as **hard-wired human approval gates**, a **demands-and-needs record kept as evidence**, and a **broker-visible audit trail with pause/resume**.
- **PMI health-data risk** (AI misreading a pre-existing condition) is the **top risk** (Section 12).

## 1.1 Decisions (change any, with a reason)

| # | Decision | Choice | Why | Alternative |
|---|---|---|---|---|
| D1 | Repo | New repo `helm-broker-portal` (monorepo). The portal **never reads the consumer database**; **API only**. | Your requirement; clean trust boundary. | Same repo (rejected). |
| D2 | Backend | **Python 3.12 + FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic.** | Same stack as the consumer backend (shared skills, shared contracts); best AI/agent ecosystem; engine is pure Python. | Node/Express. |
| D3 | **Agent framework** | **CrewAI** (≥ 1.8.0): **Flows** for the pipeline (event-driven, state, branching, loops), **Crews** for the LLM-heavy steps (A1 research, A3 narration, A4 drafting), **hierarchical Process** for the referral branch. Our own **Case state machine** is the source of truth and the control plane. | Matches your notes (sequential backbone, hierarchical referral, Flows for loops) and the docs show `@human_feedback` with `emit` routing, an **async/non-blocking feedback provider**, and a **`learn=True`** option that distils lessons from human feedback (relevant to Agent 5). | **LangGraph (Python)** if CrewAI's durability proves weaker in the P0 spike: it has mature `interrupt()` + Postgres checkpointer. Agents sit behind one interface so this swap costs one phase. |
| D4 | **Where human gates live** | In **application code + database + RBAC**: an **approval task** that stays `pending` until an authenticated human event. CrewAI's `@human_feedback` is only a *mechanism to wait*, never the control. | Your notes: *prompted caution is not a compliance control*. | Prompt-only (rejected). |
| D5 | LLM vs code | LLM = read, extract, summarise, draft, narrate. **Code = every number, gate, rule, ranking, tax, eligibility.** | Same principle as the consumer site's deterministic servicing engine. | LLM scoring (rejected). |
| D6 | Database | **PostgreSQL 16** (UK/EU region): relational integrity for approvals, **JSONB** for varied insurer quotes, **append-only hash-chained** audit table. Optional `pgvector` for the knowledge base. | Strong transactions for audit + approvals; same engine as the consumer side (Supabase Postgres). | MongoDB. |
| D7 | Long waits (the 6 hours) | **Arq (Redis) delayed jobs** + a **Clock abstraction** (`live` vs `demo`). CrewAI flow runs are **short, stateless steps** rehydrated from Postgres. | Durable timers; no process waits in memory. | **Temporal** (upgrade path: durable timers, signals, time-skipping tests) when volume grows. |
| D8 | Live updates | **Server-Sent Events** with replay (`Last-Event-ID`). | One-way activity stream; simple. | WebSockets. |
| D9 | Broker auth | **Passkeys (WebAuthn, `py_webauthn`)** first; **password (argon2id) + TOTP** fallback; rotating refresh sessions in httpOnly cookies; **step-up re-auth for approvals**. | Staff handling health data; approvals must be attributable to a person. | Managed IdP (Auth0/WorkOS/Keycloak) behind the same login UI. |
| D10 | **Website** | **React 18 + Vite, JavaScript/JSX only (no TypeScript)**, React Router, TanStack Query, Zustand, Framer Motion (`motion`), `@use-gesture/react`, Radix UI, Tailwind (tokens via CSS variables), Zod for runtime validation, Vitest + Playwright. | Your rule. Apple-like springs/gestures; accessible primitives. | Next.js (JS). |
| D11 | Consumer ↔ broker link | **Contract-first** OpenAPI 3.1; generated Pydantic models (backend) and Zod schemas (website); a **mock Core API**; **contract tests**. | Independent delivery; catches drift. | Ad-hoc calls. |
| D12 | Magic link owner | The **consumer site (Core API)** mints and emails the link when the broker publishes. | Consumer identity belongs to the consumer site. | Portal mints (Section 9.4). |
| D13 | Learning (Agent 5) | **Propose, never auto-deploy.** Daily job → *Model Change Request* needing human approval; capped, versioned. | A silently self-modifying ranking in regulated advice is indefensible. | Auto-apply within caps (off by default). |
| D14 | Scope | **PMI (personal lines) first.** A PMI recommendation is an **advised sale** (personal recommendation). Commercial / MGA referral loops from your notes → optional later phase. | Helm is a PMI broker. | — |
| D15 | LLM gateway | **LiteLLM** (CrewAI already uses it) behind our own `LLMGateway`: provider allow-list, UK/EU region pinning, **redaction before every call**, cost/token budgets, call log. Default model provider = what the consumer site uses (Groq) unless the DPIA says otherwise. | Data-protection control point (`[VERIFY]` transfers). | Direct SDK calls (rejected). |
| D16 | Observability | OpenTelemetry traces + structured logs + an LLM trace store (self-hosted Langfuse or equivalent). **No PHI in logs.** | Debug agents; audit. | — |

---

## 2. RESEARCH DIGEST — WHAT MODERN AGENTIC INSURANCE PRODUCTS DO, AND WHAT WE TAKE

### 2.1 Sources and lessons

| Source | What it does `[SOURCED]` | What we take | What we do differently |
|---|---|---|---|
| **Oscar Health** — *Superagent*, *Oswell*, AI claims assistant | Classifies intent, then runs **specialised sub-agents in parallel**; calls an internal API that **adjudicates "shadow claims" deterministically** so the AI never invents cost numbers. Oswell is a member agent grounded in claims/clinical data. Oscar reports claim escalations resolved ~50% faster (vendor claim). | Intent routing + parallel sub-agents; **deterministic calculators behind the LLM** (our engine, IPT calc); plain-language communication. | Our human gates are mandatory for advice; Oscar is a carrier. |
| **Harper** (AI-native commercial brokerage) | Agents read applications, **route across 160+ carriers**, manage quotes, chase underwriters; "1–2 days" quoting; voice AI; internal operators **document edge cases and turn human judgment into templates/workflows**. | **Judgment Notebook** (edge cases from broker overrides); chase automation; workflows as templates. | Harper aims at near-autonomous commercial placement. We keep **a licensed human on every advised recommendation**. |
| **Jointly AI Broker** (UK personal lines) | Five agents (**intake → research → quoting → analysis → delivery**); research checks providers on the **FCA register**; analysis **standardises quotes and scores them against stated priorities**; **per-field confidence**; "all actions logged in real time". The article describes **no human approval step** before the recommendation. | Nearly your A1–A5 shape; per-field confidence; FCA-register check; quote normalisation. | **We add hard approval gates and survey-driven learning** (our differentiator and compliance answer). |
| **Applied + Cytora** (email-to-quote) | Ingests an email submission, extracts risk data, applies carrier rules, returns **quote / decline / referral threaded to the submission**. | Partner replies classified as **quote / decline / referral / clarification**, threaded to the case. | — |
| **Covera, Mulligan, Semsee** | Agents for **submission intake, follow-up drafting, carrier quoting, comparison**; extract fields and **identify what is missing**; appetite matching. | Missing-info detection; follow-up drafts; appetite matching before the RFQ. | — |
| **Kay.ai** | Executes a customer's **written procedures** and refines them from feedback; the release describes **no escalation/approval process**. | **Editable playbooks** per partner/case type. | Escalation and approvals are first-class. |
| **Sixfold, Federato** | Underwriting agents learning **guidelines**; Federato stresses **data provenance behind every generated quote**. | **Provenance on every number.** | — |
| **Forrester / Teamvoy / Deloitte-style guidance** | "Augment, not replace"; HITL gives **explainability and auditability**; set HITL thresholds by **materiality, not model confidence**. | **Materiality-based gates**; decision logs; escalation triggers. | — |
| **Guidewire / Duck Creek** (2026 agentic frameworks) | Packaged agentic platforms inside core insurance systems. | Confirms direction; we integrate by API. | — |

### 2.2 Features adopted (each becomes a build item)

| ID | Feature | Origin | Phase |
|---|---|---|---|
| F1 | Per-field **confidence + provenance** on every extracted fact | Jointly, Federato | P3 |
| F2 | Intent routing + **parallel sub-agents** (CrewAI async tasks) | Oscar | P3–P5 |
| F3 | **Deterministic calculators** behind the LLM (engine, IPT, arithmetic checks) | Oscar | P5 |
| F4 | **Live Activity** with pause / resume / take over | your notes | P2, P7 |
| F5 | Partner replies classified (quote/decline/referral/clarification) | Applied/Cytora | P4 |
| F6 | **Missing-info chase** drafts + scheduled chasers (T+2h, T+4h) | Covera, Applied | P4 |
| F7 | **FCA Register check** of each partner | Jointly | P4 |
| F8 | **Playbooks** (editable operating procedures) | Kay | P4, P8 |
| F9 | **Judgment Notebook** (structured edge cases) | Harper | P8 |
| F10 | **Provenance panel**: every number links to its source | Federato | P5 |
| F11 | **Materiality-based gates** | Forrester/Teamvoy | P6–P7 |
| F12 | Quote **normalisation** into one canonical schema | Jointly, your "normalise policy terms" | P4 |
| F13 | **Uncertainty** (Monte-Carlo rank stability) and **counterfactual** ("what flips #1 vs #2") | ours | P5 |
| F14 | **Dual-audience explanations** (broker-technical / consumer-plain) | existing Helm requirement | P5–P6 |
| F15 | **Command palette**, keyboard-first, Quick Look preview | Apple-style | P1–P2 |
| F16 | **Agent Activity pill** (Dynamic-Island-style live agent status) | Apple-style | P2 |
| F17 | **Time-machine replay** of a case | ours | P7 |
| F18 | **Champion–challenger** engine versions with shadow evaluation | ours | P8 |
| F19 | **Commission-neutrality check** (ranking is commission-blind; deviations toward higher commission are flagged) | Consumer Duty | P5–P6 |
| F20 | **Medical-data firewall** (Section 12) | your PMI note | P3–P10 |
| F21 | Partner **email-in** channel; voice intake | Harper/Jointly | Roadmap |

### 2.3 Honest gaps in the research

- **"Ocean insurance":** searched; **no distinct agentic-insurance product by that name found** (results: Harper, Applied/Cytora, Covera, Kay.ai, Cara, Bind AI, Outmarket, Jointly). If you meant a specific company, send the link. Nothing here depends on it.
- **"Hamper insurance"** in your first note was read as **Harper**.
- The **"RLHF / Insurance Instruct v1"** claim in your notes could not be confirmed. Treated as an *idea*: collect clean preference data now (Section 7.9), fine-tune **later**.
- Vendor claims (speed-ups, "thousands of hours") are marketing, not evidence.

---

## 3. UK REQUIREMENTS → SYSTEM CONTROLS

> Design assumptions, **not legal advice**. A UK-qualified compliance officer must sign off.

### 3.1 Corrections and flags to your notes

| Your note | Flag |
|---|---|
| "14-day cooling-off under the Consumer Insurance (Disclosure and Representations) Act / ICOBS" | `[VERIFIED]` The cancellation right is in **ICOBS 7.1**: **14 days** for "any other contract of insurance" (PMI), **30 days** for pure protection; the period starts when the contract is concluded, or later if terms are received later (7.1.5). CIDRA 2012 concerns the consumer's **duty to take reasonable care not to misrepresent**, not cancellation. The system cites ICOBS 7.1 for cancellation and shows the CIDRA duty on the fact-find. |
| "IPT standard 12%, higher 20% for some classes" | `[SOURCED]` PMI is in the **12%** band; 20% applies to e.g. travel and some motor; life and long-term care are exempt. For PMI the engine uses `IPT_STANDARD_RATE` from config (never a literal). `[VERIFY]` at build. |
| "Commission/remuneration disclosure (Consumer Duty sharpened this)" | `[SOURCED]` **CP26/22** (FCA consultation, closed 4 Sep 2026) **proposes removing** several ICOBS 4 disclosures including the *nature and basis of intermediary remuneration*, relying on Consumer Duty fair-value evidence. It is a **proposal**; final rules may be near. **Design: disclosure content is a versioned rule pack with effective dates.** Default = show remuneration until compliance changes it. |
| Generic general-insurance / commercial examples (MGA referral, warranties) | Helm is **PMI personal lines**. The recommendation is an **advised sale** → ICOBS 5.3 duties. Commercial referral loops kept as optional later phase; the referral gate (G3) is built generically. |
| "Insurance Distribution Directive (retained UK law)" | `[VERIFY]` IDD-derived rules now sit in UK legislation and the FCA Handbook (ICOBS, PROD). Cite Handbook rules. |
| "Fair analysis of market" | `[VERIFY]` Wording depends on current ICOBS text and whether Helm is whole-of-market or a panel. The pack always states the **search basis** (whole market / panel of N insurers). |

### 3.2 Control register (enforcement = code, not prompt)

| Ctl | Obligation (source) | Control implemented | Enforced by | Evidence |
|---|---|---|---|---|
| C1 | **Establish demands & needs** before recommending (ICOBS 5.2/5.3.2G) `[page read; wording VERIFY]` | **Demands & Needs Record (DNR)**: structured, versioned, each field with source and timestamp; broker **signs off the DNR** before RFQs go out | Guard `FACTFIND_READY → RFQ` requires `dnr.signed_off_by` | DNR versions, sign-off event |
| C2 | **Reasonable care to ensure suitability** (ICOBS 5.3.1R) `[VERIFIED]` | Code-run suitability checklist; unmet needs listed; broker confirms | Gate G2 | Suitability record |
| C3 | **Personalised explanation of why the contract best meets the needs** (ICOBS 5.3.4R) `[VERIFIED]` | A4 drafts; **authorised broker edits and approves**; stored verbatim | Gate G2 | Statement + diff vs draft |
| C4 | **Record the assessment, recommendation and reasons; keep ≥ 3 years if the customer proceeds** (ICOBS 5.3.2BR as read; scope `[VERIFY]`) | Immutable snapshots; retention default **7 years** (policy choice) `[VERIFY]` | DB immutability + retention job | Snapshot hashes |
| C5 | **IPID** per product shown | Pack refuses to publish a plan without `ipid_url` + version | Pack validator | Manifest |
| C6 | **Cancellation notice** (ICOBS 7.1.1, 14 days) `[VERIFIED]` | Pack includes notice + start-date logic | Pack validator | Manifest |
| C7 | **IPT breakdown** | Premium = base + IPT shown separately; arithmetic gate | Engine gate + validator | Calculation record |
| C8 | **Remuneration / fair value** | Rule-pack disclosure + fair-value panel; engine **commission-blind** (unit-tested) | Rule pack + test | Disclosure record |
| C9 | **TOBA** / terms of business | Partner must have `toba_status = active` to receive an RFQ | RFQ guard | TOBA ref |
| C10 | **Market search basis** statement | Pack prints basis + partner count | Pack validator | Manifest |
| C11 | **Consumer Duty** (4 outcomes, 3 cross-cutting rules) | Plain-language explanation; comprehension testing; outcome metrics | Evals + monitoring | Evidence pack |
| C12 | **Vulnerable customers (FG21/1)** `[SOURCED]` | Vulnerability flags in DNR; flagged cases route **human-led**, no automated nudges | Router rule | Flag events |
| C13 | **Complaints (DISP; 8-week final response; FOS)** | Any message that *could* be a complaint is frozen for a human owner; agents cannot reply or close | Gate G4 | Complaint file |
| C14 | **UK GDPR Art 9 (health), Art 22, DPIA** `[VERIFY]` | Medical-data firewall; human decision on every recommendation; DPIA before launch | Section 12 | DPIA, ROPA |
| C15 | **International transfers** (LLM host) `[VERIFY]` | Redaction before any LLM call; provider allow-list; region pinning; DPA | LLM gateway | LLM call log |
| C16 | **CASS 5** client money `[VERIFY]` | **v1 holds no client money**: premium paid direct to insurer; bind deferred | Scope rule | — |
| C17 | **FCA authorisation / approved persons** | Only users with `fca_irn` and `can_approve_advice` pass G2; firm FRN on the pack | RBAC | User register |
| C18 | **Audit and explainability** | Append-only, hash-chained log; broker can watch any case live; evidence export | Audit service | Export |
| C19 | **Equality / fairness** | Ranking uses no protected characteristics; outcome metrics disaggregated | Engine design + monitoring | Fairness report |
| C20 | **AI governance** (FCA AI perimeter debate, Mills Review Jul 2026) `[SOURCED]` | Model registry; versioned engine/weights/prompts; change control; rollback | §7.9, P8 | Model cards |

### 3.3 Hard human gates

| Gate | Blocks | Who may pass | Trigger | Enforcement |
|---|---|---|---|---|
| **G0 DNR sign-off** | RFQ release | Any broker | DNR complete | `approvals` row + guard in `CaseService` |
| **G1 RFQ release check** | Sending consumer data to partners | **Rules** (consent present, data minimised, appetite, TOBA); a **broker** if any medical free-text is present | Always evaluated | Rules engine; broker approval if medical text |
| **G2 Suitability & publish** | Anything reaching the consumer | **`authorised_broker` only**, **step-up re-authentication** | Always (advised sale) | Approval task + RBAC + step-up token |
| **G3 Referral / non-standard** | Accepting non-standard terms; any "referred" terms | Broker (and partner underwriter) | Partner returns referral/counter-terms | State `UW_REFERRAL` |
| **G4 Complaint** | Any reply or closure | Designated complaint owner | Classifier OR any dissatisfaction wording | State `COMPLAINT_FLAGGED`; agents locked out |
| **G5 Model change** | Activating a new weight set | Compliance officer **and** lead broker (four-eyes) | Agent 5 proposal | `model_change_requests` workflow |

Agents **cannot** call the transition functions behind G0, G2, G3, G4 or G5. A test that attempts this must fail (Section 13).
