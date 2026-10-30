# Main-plan P5–P9 decisions and evidence

## Ranking and broker review

The supplied Python and JavaScript engines are preserved under `packages/engine`. All 18 Python methods and 16 JavaScript tests pass. The omitted golden-vector file is generated from the supplied JS oracle for 40 independent contexts; unrounded quantities use the supplied 1e-9 parity tolerance. The API calls the package for weights, utilities and initial aggregation. Its Monte Carlo hot loop avoids the reference's unused presentation rounding, while the independent scalar and invariant checks preserve numerical behaviour. Historical snapshots remain unchanged.

Every current shortlisted plan requires stars (1–5), YES/NO/REFER and a trimmed written assessment of at least 20 characters. The server chooses the draft used for edit distance; client-supplied draft text cannot forge the flag. P5 explicitly permits saving an unchanged reason with a warning, so that flag is preserved for review and learning. There is no one-click “accept draft” action. A changed assessment creates an immutable version bound to the ranking, plan evidence and broker; the current view restores the latest version. Another broker must record their own assessments. Exactly three plans with YES decisions can be selected and ordered using drag/drop or keyboard-accessible buttons.

The pack binds all five assessment records and their hash. G2 verifies the same broker and current ratings, all three suitability confirmations, the overall declaration, current G0 evidence, unmet-need acknowledgements and a fresh, one-use, session-bound proof. A metadata-only G2 event records the proof hash. Approval commits before the durable publication job contacts Core. The existing request-changes action returns to comparison for a new review; neither agents nor malformed/incomplete evidence can cross the gate.

## Human exceptions and learning

Complaint intake preserves an encrypted original and assigns the designated compliance owner. Only that owner can resolve it; resolution also creates an immutable snapshot. Agent work remains held until closure of the complaint restores the prior state. The 56-business-day interval is compressed by the configured demo clock; the applicable live response policy requires compliance review. G3 remains a fictional underwriter-reference workflow. The canonical H1–H10 registry takes precedence over conflicting phase aliases.

A5 keeps disputed cases out, holds out cases from training, discounts unedited assessments and excludes referred alternatives from rating comparisons. Shadow mode and promotion both retain independent compliance/lead approvals. Promotion requires at least 30 new labelled cases and at least 0.02 NDCG@3 improvement. It never activates automatically. Existing rollback and separate playbook approval remain available. These fictional tests do not establish representative ranking quality or fairness.

## Consumer handoff and closure

Signed, timestamp-checked Core events handle acceptance, decline, partial response, link open/expiry and binding confirmation. The event must name the current approved pack hash; accepted/bound plans must be in the approved set. Replaying an identical event is idempotent; reusing its ID with different content is rejected. Free-text consumer details and policy references remain encrypted; SSE/audit messages contain metadata only. Browser notifications are used only if permission is already granted.

The canonical state graph has no DECLINED state, so a decline records its outcome and closes the case. Acceptance stays Published until a matching binding event arrives. This service performs no purchase, payment or real binding. A closure PDF is encrypted in an immutable snapshot, has a SHA-256 checksum, omits medical text and reduces ratings to plan/stars/decision. Quote evidence is finalised through a snapshot rather than by mutating historical plan rows.

The P9 instruction to multiply an IPT-inclusive annual premium by 12% conflicts with the plan's integer-pence premium arithmetic. Closure preserves the approved breakdown (`annual = base + IPT`); e.g. a £1,120 annual premium consists of £1,000 base plus £120 IPT. Conflicting six/seven-year retention examples remain a proposed six-year policy-review job, with no automatic destruction of immutable evidence. Named legal/compliance owners must approve the retention policy and deletion design before live use. No statutory retention claim or legal signature is fabricated.
