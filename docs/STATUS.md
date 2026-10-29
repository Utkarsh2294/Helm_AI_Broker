# Prototype status

The complete specification is preserved at `docs/spec/HELM_BROKER_PORTAL_PROJECT.md`. P0–P11 prototype work includes the five agents, human gates, authentication, partner scenarios, governance, evidence/replay and operational tooling. See [the phase evidence ledger](phases/EVIDENCE.md) for actual checks and remaining acceptance items.

The default workspace is fictional and single-firm. MockCore is a demonstration boundary. The project has no payment or client-money endpoint. Local code supplies deterministic extraction and narratives; optional provider calls remain disabled without verified configuration. A working prototype does not establish the suitability of real insurance advice.

The missing original worked-example fixture and conflicting reference-band instructions are documented in `docs/phases/BASELINE.md`. An independent JavaScript oracle and property tests verify the implemented arithmetic, without claiming parity with an unavailable fixture.

Live insurer/Core contracts, adviser verification, mandatory MFA policy, legal wording, provider contracts/regions, representative OCR/unstructured extraction, KMS/rotation, external write-once anchoring, alert delivery, retention and calibrated outcome monitoring remain launch gates. Dependency advisory findings and measurements that miss a target are recorded, not presented as green checks.

Read [the launch checklist](launch-checklist.md), [DPIA draft](dpia/helm_broker_portal_dpia.md), [model card](model-cards/engine-v1.1.md) and [operator guide](runbooks/operator-guide.md) before connecting real data.
