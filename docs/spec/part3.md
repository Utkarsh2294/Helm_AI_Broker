
---

# PART 3 — RECOMMENDATION ENGINE, DATA, API

## 7. THE RECOMMENDATION ENGINE (modern, explainable, verified)

Code: **Appendix A** (Python, production) with tests (Appendix B). **Appendix C** is the JavaScript reference it was checked against. Wire keys are camelCase (shared with the website); Python function names are snake_case.

### 7.1 Design principles

1. **Deterministic and reproducible.** Same inputs + same `engine_version` + same `weights_version` → identical output. Monte-Carlo uses a seeded RNG (seed = hash of ranking id).
2. **Gates before scores.** Hard requirements are **non-compensatory**: a plan missing a must-have is *excluded with a reason*, not penalised.
3. **Absolute utilities, no rank reversal.** Each criterion utility is in `[0,1]` computed from the plan and the consumer's needs only, never "relative to the best plan in this batch". Adding or removing a quote cannot reorder the others (unit-tested by dropping each plan in turn). Classic TOPSIS/AHP suffer rank reversal because their ideal points depend on the batch; we use **fixed** ideal (all 1) and anti-ideal (all 0).
4. **Explainable to the point.** Score = sum of per-criterion **points** (`100·w·u`) + a "balance" term; the UI shows every point.
5. **Commission-blind.** Commission is not an input to any utility (unit-tested). It is shown separately in the fair-value panel.
6. **No protected characteristics** are inputs. Age influences *premiums* (set by insurers) but not our weights.
7. **LLM never touches a number.**

### 7.2 Pipeline

```
quotes ─► canonical plans ─► GATES ─► utilities u_c ─► weights w_c ─► score
                                │                          │
                                └─ excluded + reason       └─► rank ─► diversify (≤2/insurer) ─► top 5
                                                                   └─► Monte-Carlo stability ─► tie banding
                                                                   └─► flip analysis ─► explanation (numbers grounded)
```

### 7.3 Criteria and utilities (all in [0,1])

Notation: `clamp(x)=min(1,max(0,x))`. Money in pence.

**1. Affordability** — total expected annual cost, judged against the consumer's budget (soft) and the market (reference):

```
TECO      = annualPremium + claimFreq · min(excess, expectedClaim)        (defaults 0.25, £3,000)
u_budget  = 1 / (1 + exp(6 · (TECO / budget − 1)))                       (logistic: 0.5 at budget)
u_ref     = clamp((p90 − TECO) / (p90 − p10))                            (market benchmark band)
affordability = 0.5·u_budget + 0.5·u_ref
```

**2. Coverage fit** — importance-weighted attainment of the consumer's desired levels:

```
coverage = Σ_k importance_k · clamp(planLevel_k / max(desiredLevel_k,1)) / Σ_k importance_k
```

**3. Network** — hospital list vs desired, plus share of the consumer's preferred hospitals:

```
network = 0.6 · clamp(hospitalListLevel / desiredHospitalLevel) + 0.4 · clamp(preferredHospitalShare)
```

**4. Underwriting terms** — exclusion burden and match to the consumer's preferred underwriting basis:

```
burden       = clamp(Σ exclusionSeverity / maxSeverity)
underwriting = 0.7·(1 − burden) + 0.3·(1 if type == preferred else 0.5)
```

**5. Insurer quality** — complaint-uphold rate **shrunk toward a prior** (so a new insurer with 3 complaints isn't over-trusted), financial strength, service level:

```
shrunkUphold  = (n·upheldRate + n0·p0) / (n + n0)            n0 = 30, p0 = 0.25
insurer_quality = 0.5·(1 − shrunkUphold) + 0.3·finStrength + 0.2·slaScore
```

**6. Process ease** — the "docs required" part of your brief:

```
process_ease = clamp(1 − 0.6·(docsUnavailable / docsRequired) − 0.4·min(turnaroundDays/14, 1))
```

**7. Terms clarity** — IPID completeness, plain-language score, fewer exclusions:

```
terms_clarity = clamp(0.5·ipidCompleteness + 0.3·plainLanguage + 0.2·(1 − min(exclusionsCount/20, 1)))
```

### 7.4 Weights

- **User priorities → weights** with **Rank-Order Centroid (ROC)**: for `m` ranked criteria, `w_i = (1/m) Σ_{k=i..m} 1/k` (m=3 → 0.611, 0.278, 0.111). Ranked criteria share **85%** of the mass; unranked share **15%** equally. (ROC turns "my top three are A, B, C" into weights without asking people for numbers.)
- **Learned weights** (Agent 5) never replace user weights. `combine_weights` blends with `λ ≤ 0.25`, then projects the result so **every criterion stays within ±30% of the user-derived weight (floor 0.02) *after* normalisation** (bisection on a common shift). *(Bug found and fixed in this build: clamp-then-renormalise let a weight rise +57%.)*

### 7.5 Hard gates (non-compensatory)

A plan is **excluded** (with reason) if: status ≠ `quoted`; over a hard budget cap; a **must-have** coverage level is not met; underwriting type not allowed. A plan is **routed to a human** (not scored) if: `premium_arithmetic_mismatch` (annual ≠ base + 12% IPT beyond tolerance) or `medicalFlagsAmbiguous` (wording touching pre-existing/related conditions could not be mapped to structured terms). Reasons are shown to the broker.

### 7.6 Aggregation (fit + balance)

```
wsm     = Σ w_c · u_c                           (additive fit, 0..1)
d+      = sqrt(Σ w_c · (1 − u_c)²)              (distance to fixed ideal)
d−      = sqrt(Σ w_c · u_c²)                    (distance to fixed anti-ideal)
balance = d− / (d+ + d−)                        (TOPSIS-style closeness, 0..1)
score   = 100 · (0.7·wsm + 0.3·balance)
points_c = 100 · w_c · u_c                      (Σ points_c = 100·wsm  — shown in the UI waterfall)
```

`balance` rewards plans that are good *across* criteria (not one great, one terrible); `wsm` keeps the arithmetic transparent. Ties are broken by plan id for determinism.

### 7.7 v1.1 additions (SPECIFIED, **not yet in Appendix A** — implement in P5 with tests)

The verified worked example (7.8) exposed two things the UI must handle:

1. **Tie banding.** If `score_1 − score_2 < 1.0` **or** `pTop1` of #1 < 0.65, label ranks **"joint #1"** and say so in the explanation. (In the example: margin 0.26, pTop1 0.49 vs 0.51.) Never present a coin-flip as a clear winner.
2. **Blockers overlay (do not change the score).** Raise a red chip and require an **explicit broker acknowledgement** before a plan can be selected when: `docsUnavailable/docsRequired > 0.5`; `ipidCompleteness < 0.6`; `turnaroundDays > 10`; `medicalFlagsAmbiguous`; insurer FCA status not `authorised`. (In the example, plan D1 ranks #2 although 3 of its 5 required documents are unavailable, because `process_ease` carries only 3.7% weight; a human must see that.)
3. **Commission-neutrality check.** Compute `corr`/rank gap between the engine order and commission order; if the broker's selection moves toward higher commission than the engine order by more than a threshold, write an audit flag `commission_deviation` for compliance review (not a block).

### 7.8 Worked example (synthetic; numbers from the verified run)

Consumer priorities: **affordability > coverage > network**. Weights → affordability 0.519, coverage 0.236, network 0.094, other four 0.037 each. Must-have: cancer level 3. Budget £900/yr.

| Rank | Plan | Score | Fit | Balance | P(rank 1) over 1,000 weightings | Notes |
|---|---|---|---|---|---|---|
| 1 | A1 | 77.1 | 78.1 | 74.6 | 0.491 | cheapest eligible, full coverage |
| 2 | D1 | 76.8 | 77.9 | 74.2 | 0.509 | process_ease 0.30 (3 of 5 documents unavailable) |
| 3 | B1 | 69.2 | 70.3 | 66.8 | 0 | underwriting 0.5 (FMU + exclusions) |
| 4 | A2 | 65.9 | 67.1 | 63.2 | 0 | broader cover, pricier |
| 5 | C1 | 61.1 | 62.2 | 58.4 | 0 | best network, highest cost |

**Excluded:** A3 (`must_have_missing:cancer`); E1 (`premium_arithmetic_mismatch` → human). **Flip analysis #1 vs #2:** margin 0.26 points; moving **0.01** of weight from process_ease to affordability swaps them. **Reading:** A1 and D1 are a **statistical tie**; D1 carries a **blocker**. This is exactly what the broker should see.

### 7.9 Survey and learning data (Agent 5 input)

**The survey is designed to take under 10 seconds** (a bottom sheet shown at selection):

| Question | Control | Required |
|---|---|---|
| For **each selected plan**: "Did the engine's score and explanation look right?" | 👍 / 👎 | 👍/👎 required |
| If 👎: reason | chips: *Price ranked too high/low · Ignored a must-have · Network wrong · Insurer concern · Document burden · Other* | optional |
| "Engine's #1 wasn't selected — why?" (only when true) | same chips | required in that case |
| "How clear was the explanation?" | 5 dots | optional |
| Note | 140 characters | optional |

**Turning feedback into training signal:**

- **Pairs:** selected ≻ not-selected among the engine's top 5 (weight 1.0); order among the three selected (weight 0.5).
- **👍** keeps full weight. **👎** marks the sample `disputed`: **excluded from weight learning until a reviewer reads it**, and sent to the **Judgment Notebook** instead (a dispute is often a data/gate problem, not a weight problem).
- **Learning step:** Bradley–Terry with temperature β = 8 over the **linear score** difference, MAP prior on current log-weights (L2 pull), then **evidence shrinkage** `a = n/(n+50)`, then **`combine_weights` caps**. Minimum 30 new comparisons per run, else no proposal.
- **Metrics:** NDCG@3 and top-3 agreement vs broker choice (champion vs challenger on held-out cases), survey 👍 rate, explanation clarity, override reasons trend.
- **Governance:** proposal → **G5** (compliance + lead broker) → **shadow mode** → promote → rollback ready; all weight sets versioned in `engine_models`.
- **Fine-tuning later:** the same de-identified pairs + rationale tags become a supervised/preference dataset (DPO-style) to fine-tune a *term-normalisation* model; **not** the ranking maths.

### 7.10 Uncertainty and counterfactuals

- **Monte-Carlo stability:** draw weights from a Dirichlet centred on the current weights (concentration κ = 60); re-score; report `pTop1`, `pTop5`, mean rank, 95% score interval per plan.
- **Flip analysis:** smallest shift of weight (step 0.01, max 0.30) from one criterion to another that swaps two plans' order.

### 7.11 Verification status

| Property | Test | Result |
|---|---|---|
| ROC weights textbook values | JS+PY | pass |
| Weights sum to 1; cap & floor hold **after** normalisation | JS+PY (+40 random cases) | pass (bug fixed) |
| Gates exclude / route to human; not scored | JS+PY | pass |
| Score ∈ [0,100]; points sum = fit | JS+PY | pass |
| Cheaper never lowers score (monotonic) | JS+PY | pass |
| **No rank reversal** (drop-one) | JS+PY | pass |
| **Commission-blind** | JS+PY | pass |
| Deterministic; seeded Monte-Carlo reproducible | JS+PY | pass |
| Diversity ≤ 2 per insurer | JS+PY | pass |
| Learning bounded by shrinkage and caps | JS+PY | pass |
| **Python ≡ JavaScript on 40 random scenarios (1e-9)** | parity | pass |

**Not yet verified / known limits:** the constants (logistic steepness 6, 0.5/0.5 and 0.7/0.3 mixes, n0 = 30, κ = 60, β = 8) are **priors, not fitted**; calibrate in P8 with real broker choices. Coverage levels are ordinal 0–3 and need a mapping table per insurer (done in normalisation). v1.1 additions (7.7) are specified only. Real-world ranking quality is unmeasured until brokers use it.

### 7.12 Methods considered and rejected

| Method | Why not (as the core) |
|---|---|
| Plain TOPSIS | Rank reversal when the batch changes; we keep its *balance* idea with fixed anchors. |
| AHP pairwise weights | Too much user effort (many comparisons); ROC from a simple priority order is enough. |
| Entropy weights | Weights depend on the batch spread → rank reversal. May be shown as a *diagnostic* ("which criteria discriminated here"). |
| Fuzzy MCDM | Adds opacity without evidence of better outcomes here. |
| LLM-as-scorer | Not reproducible, not auditable, hallucination risk. LLM only narrates. |
| Learning-to-rank (GBDT) | Needs far more data; revisit after thousands of decisions; keep the transparent engine as champion. |

---

## 8. DATA MODEL (PostgreSQL)

All ids `uuid`. Timestamps `timestamptz` (UTC). Money `bigint` pence. Sensitive columns (medical text, free-text notes, contact data) use **application-level field encryption** (AES-GCM, keys in a KMS, key id stored per row). Soft-delete is not allowed on evidential tables.

| Table | Key columns | Notes |
|---|---|---|
| `orgs`, `users` | email, name, role, `fca_irn`, `can_approve_advice`, `mfa_required`, `status` | Roles: `authorised_broker`, `broker_assistant`, `compliance_officer`, `admin`, `auditor` |
| `credentials_passkey`, `credentials_password`, `totp_secrets`, `recovery_codes` | user_id, public key / argon2id hash / encrypted secret | |
| `sessions` | user_id, family_id, refresh_hash, ip, ua, created, last_seen, revoked_at, `step_up_at` | Rotation with reuse detection |
| `cases` | core_request_id, state, assigned_to, priority, cover_type, sla_due, `paused_reason`, version | **State machine owner** |
| `dnr` (versioned) | case_id, version, status, `body jsonb` (encrypted subset), signed_off_by/at, `body_hash` | Immutable once signed off |
| `rfqs` | case_id, dnr_version, canonical body, deadline, clock_mode | |
| `rfq_partner_status` | rfq_id, partner_id, sent_at, last_chase_at, state, response_count | |
| `partners` | core_partner_id, name, fca_ref, toba_status, appetite jsonb, sla_hours | cache of Core data |
| `partner_messages` | rfq_id, partner_id, direction, raw (encrypted), classification, injected_flag | raw kept for evidence |
| `quotes` | rfq_id, partner_id, revision, raw jsonb, canonical jsonb, flags, `canonical_hash` | revisions never overwritten |
| `rankings` (immutable) | case_id, quote_set_hash, dnr_version, engine_version, weights_version, `inputs_hash`, results jsonb, mc jsonb, flags | |
| `selections` | ranking_id, selected plan ids (ordered), by_user, `edited_reasons` | |
| `surveys` | selection_id, per-plan thumb, reason chips, clarity, note | |
| `suitability_statements` | case_id, version, draft_text, final_text, diff, approved_by | |
| `packs` | case_id, manifest jsonb, `pack_hash`, rule_pack_version | published snapshot |
| `approvals` | case_id, gate, approver_id, step_up_at, payload_hash, decision, comment, at | The **control** |
| `publications` | case_id, core_recommendation_id, delivered_at, viewed_at, outcome | |
| `activity_events` | seq, case_id, ts, actor_type, actor_id, type, payload (redacted), `prev_hash`, `hash` | **append-only**, DB role has no UPDATE/DELETE |
| `agent_runs`, `tool_calls`, `llm_calls` | run id, agent, model, prompt_hash, tokens, cost, latency, redaction_report | no raw PHI |
| `engine_models` | version, weights jsonb, status (`champion|challenger|retired`), created_by, change_request_id | |
| `model_change_requests` | proposed weights, evidence jsonb, metrics jsonb, status, approvals (2) | G5 |
| `edge_cases` (Judgment Notebook) | case_id, tags, description, resolution, links | |
| `complaints` | case_id, owner_id, received_at, **due_final_response_at (+8 weeks)**, status | G4 |
| `consent_records` (mirror) | core_consent_id, purpose, text_version, at | |
| `playbooks` | scope, version, steps jsonb, approved_by | F8 |
| `jobs_log` | job, case_id, scheduled_for, ran_at, result | |

**Audit hash chain:** `hash = SHA-256( prev_hash ‖ canonical_json(event_without_hash) )`, per case. A nightly job verifies every chain and writes a **daily root hash** to write-once storage; a mismatch raises a P1 alert. **Evidence export** = JSON + PDF containing the DNR versions, quotes (raw + canonical), ranking snapshot, survey, suitability draft/final + diff, approvals, pack, and the verified chain.

**Retention** (policy, `[VERIFY]`): evidential tables 7 years; LLM call metadata 13 months; raw partner messages 7 years; sessions 90 days; de-identified learning data until withdrawn.

---

## 9. API SURFACE (broker portal)

Base `/api/v1`. JSON. Auth by cookie; CSRF header on mutating calls.

### 9.1 Auth
`POST /auth/identify` (email → available methods, no user enumeration) · `POST /auth/passkey/options|verify` · `POST /auth/password` · `POST /auth/totp/verify` · `POST /auth/step-up` · `POST /auth/refresh` · `POST /auth/logout` · `POST /auth/logout-all` · `GET /auth/session` · `GET /auth/devices` · `DELETE /auth/devices/{id}` · `POST /auth/passkeys/register` · `POST /auth/recovery`

### 9.2 Cases and workflow
`GET /cases?state&assignee&q&cursor` · `GET /cases/{id}` · `POST /cases/{id}/assign` · `POST /cases/{id}/pause` · `POST /cases/{id}/resume` · `POST /cases/{id}/take-over` · `GET /cases/{id}/dnr` · `PATCH /cases/{id}/dnr` (tracked edit with reason) · `POST /cases/{id}/dnr/sign-off` (G0) · `GET /cases/{id}/rfq` · `POST /cases/{id}/rfq/release` · `GET /cases/{id}/quotes` · `GET /cases/{id}/ranking` · `POST /cases/{id}/selection` (+ survey) · `GET|PUT /cases/{id}/suitability` · `GET /cases/{id}/pack` · `POST /cases/{id}/approve` (G2, needs step-up) · `POST /cases/{id}/request-changes` · `GET /cases/{id}/evidence` (export)

### 9.3 Observability and governance
`GET /cases/{id}/events?after=` · **`GET /cases/{id}/stream` (SSE)** · `GET /cases/{id}/events/{seq}/explain` · `GET /cases/{id}/replay?at=` · `GET /complaints` · `POST /complaints/{id}/…` · `GET /partners` · `PATCH /partners/{id}/playbook` · `GET /insights/*` · `GET /models` · `GET /model-change-requests` · `POST /model-change-requests/{id}/approve|reject` · `GET /audit/search` · `GET /admin/users` …

### 9.4 Magic link (consumer side)
- **Owner:** Core API. Portal calls `POST /v1/recommendations` with the **G2 approval id** and the immutable pack; Core stores it and emails the link.
- **Token:** ≥ 128-bit random, **only a SHA-256 hash stored**, bound to the consumer account and the recommendation id, **single use**, expires (`[DESIGN]` 48 h to first use; a *resend* flow exists), exchanged **server-side** for a short session; the email contains **no health data and no premium figures**.
- **Sensitive actions** (accept, ask a question about health, change details) require a **step-up** (emailed 6-digit code or passkey) even inside the session.
- **Forwarded link defence:** first open requires entering a code sent to the same email (optional per policy); all uses logged; revoke on suspicion.
- **Monitoring:** token reuse attempts, expiry rejections, delivery delay alerts.
