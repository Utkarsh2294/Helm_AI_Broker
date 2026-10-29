# Helm recommendation engine — prototype model card

Deterministic multi-criteria ranking, with a seeded Monte Carlo sensitivity analysis. Inputs are canonical policy attributes and recorded consumer priorities. Commission is excluded from scoring. Outputs include five leading plans, criterion points, blockers, score intervals, joint-first indication and a weight-shift explanation.

The reference premium band stays fixed so removing a competing quote does not change other quotes' scores. The supplied blueprint also requested recomputing percentile bands; those requirements conflict. The baseline decision and independent JavaScript oracle are recorded in `docs/phases/BASELINE.md`.

Constants, ordinal coverage levels and reliability priors require calibration. No live recommendation-quality claim is made. MC intervals describe sensitivity to sampled priorities, not probabilities that a policy is suitable. The leading tie band is a review aid. Insurer terms and underwriting remain authoritative.

Learning uses undisputed selections, case-separated validation, Bradley–Terry fitting, evidence shrinkage and bounded blending. Equal held-out performance cannot justify a challenger. Independent compliance and lead-broker approvals are required for shadow mode and promotion; at least twenty new labelled shadow cases must improve NDCG@3. Rollback restores the preceding champion.

Default extraction, ranking explanations and suitability drafting run local code. The optional CrewAI adapter has a real persisted human-feedback smoke test. Paid-provider extraction, document OCR, provider residency, original unpublished worked-example parity, live fairness monitoring and calibration on 200+ real choices remain release work. No protected characteristic is a ranking input; that alone does not establish fairness.

Owner: to be assigned. Compliance approval: pending. Version and approved deployment: pending.
