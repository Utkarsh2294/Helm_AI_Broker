# Helm recommendation engine — prototype model card

Deterministic multi-criteria ranking, with a seeded Monte Carlo sensitivity analysis. Inputs are canonical policy attributes and recorded consumer priorities. Commission is excluded from scoring. Outputs include five leading plans, criterion points, blockers, score intervals, joint-first indication and a weight-shift explanation.

The reference premium band stays fixed so removing a competing quote does not change other quotes' scores. `helm-engine==1.0.0` contains the supplied Appendix A mathematics; the API version is `helm-engine-1.0.0+broker-policy-v2`. Its adapter retains validated inputs, neutral missing-coverage handling and stricter arithmetic gates. Eighteen supplied Python tests, sixteen supplied JavaScript tests and forty independently generated JavaScript golden scenarios pass. The original blueprint's cohort-relative band example is superseded by the main plan's fixed-reference contract. See `packages/engine/README.md`.

Constants, ordinal coverage levels and reliability priors require calibration. No live recommendation-quality claim is made. MC intervals describe sensitivity to sampled priorities, not probabilities that a policy is suitable. The leading tie band is a review aid. Insurer terms and underwriting remain authoritative.

Learning uses undisputed selections and all-plan stars/decisions, case-separated validation, Bradley–Terry fitting, evidence shrinkage and bounded blending. Unedited reasons reduce sample weight and referrals are held out of those comparisons. Equal held-out performance cannot justify a challenger. Independent compliance and lead-broker approvals are required for shadow mode and promotion; at least thirty new labelled shadow cases and an NDCG@3 improvement of at least 0.02 are required. Rollback restores the preceding champion.

Default extraction, ranking explanations and suitability drafting run local code. A1 has a two-agent sequential CrewAI crew using a local model fixture and minimised context, plus a real persisted human-feedback smoke test. Paid-provider extraction, document OCR, provider residency, live fairness monitoring and calibration on representative real choices remain release work. No protected characteristic is a ranking input; that alone does not establish fairness.

Owner: to be assigned. Compliance approval: pending. Version and approved deployment: pending.
