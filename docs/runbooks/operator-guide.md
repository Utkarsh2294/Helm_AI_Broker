# Prototype operating guide

## Start and stop

Run `docker compose up --build` for PostgreSQL, Redis, API, worker, production web preview, MockCore and the partner simulator. The web workspace is `http://127.0.0.1:5180`, API readiness is `/api/v1/health`, and MockCore is on port 8011. Keep the volumes and `.runtime/demo.key`; do not remove them during an upgrade. Local Windows development uses `scripts/start.ps1 -Install` and `scripts/stop.ps1`. Its Python environment lives under `%LOCALAPPDATA%/HelmBroker/venv` to avoid OneDrive file locking. Start PostgreSQL/Redis with Compose before the local preview. Run Alembic migrations before starting the API.

Demo identities are broker, assistant, compliance, auditor and lead at `@helm.demo`, all initially using `HelmDemo!2026`. The assistant may review G0; only an authorised adviser may release quotations or approve advice. Compliance and the designated lead broker are separate G5 reviewers. These fictional identities and identifiers must not be carried into production.

## Case journey

The separate partner simulator is the seventh Compose service. For unreliable Docker DNS, run `scripts/build-containers.ps1 -PrepareWheelhouse`; later builds can reuse `%LOCALAPPDATA%/HelmBroker/linux-wheels`. The script verifies locked wheel hashes and hydrates source bytes into a fresh build context outside OneDrive, avoiding cloud-placeholder errors. Do not delete the download cache or any database/key volumes when retrying.

Create a fictional request. Review its facts and source references. Edit stated requirements with a reason; the form saves a fresh version after a short pause. Resolve ambiguous medical wording through the case-bound reveal and review controls, then acknowledge and sign off the DNR. Authorise a minimised RFQ and select one of the eight scenarios. The default clock compresses six business hours to six seconds. Review every shortlisted plan with stars, a Recommend/Exclude/Refer decision and a written reason. Save all five assessments before selecting and ordering exactly three recommended policies. Address every unmet need, confirm suitability of all three and the overall declaration, review the statement and save the review confirmations. Authenticate again and approve the exact pack and assessment hashes.

With Core delivery disabled, publication is a clearly labelled local simulation. With delivery enabled, a committed approval creates a durable publication job. The case becomes Published only after Core acknowledges. A failed request is retried at most three times; expiry or exhausted retries require human review. An approval older than five minutes must not be silently reused. Inspect queued job status and the audit trail before intervening.

## Halts and partner scenarios

H1 is invalid structured output; H2 is low-confidence required information; H3 is premium arithmetic; H4 is contradictory revisions; H5 is ambiguous medical wording; H6 is absent consent; H7 is an unknown or ineligible partner; H8 is an exhausted integration operation; H9 is a budget limit; H10 is prohibited output. Correct source data or the integration fault, record the review and use the allowed case action. Do not edit immutable evidence or bypass a gate in SQL. Only the implemented simulator G3 action accepts fictional underwriter confirmation; a real referral requires verified partner evidence.

## Evidence and replay

Export JSON or PDF from the case workspace. The package has fourteen sections, an audit verification result, content hash and a control-evidence checklist. Medical statements are redacted by default. Only permitted roles may explicitly request their inclusion. Keep exported files in an approved location. A report whose chain verification fails must be escalated. Use the time-machine slider to inspect historical states; return to the present before editing. Replay does not undo an action.

## Governance and complaints

Run a learning evaluation after collecting sufficient undisputed choices. A proposal that does not improve held-out NDCG cannot enter shadow mode. Compliance approves first, then a distinct lead broker. Shadow results do not alter the advice shown to a broker. Promotion requires fresh independent decisions and sufficient new labelled cases with better results. Compliance can roll back a promoted model. Review disputed feedback in the notebook and submit guidance as a new playbook version for a separate compliance reviewer.

A complaint hold stops jobs immediately. The compliance owner must investigate, preserve records and record a resolution. The prototype's 56-day reminder is an operational placeholder; compliance must verify the applicable response timetable, first receipt date, final-response wording and referral rights before live use. No external complaint email is sent by this application.

## Incidents and recovery

Set `HELM_AGENTS_PAUSED=true` to stop new agent job processing, then restart the relevant processes. Preserve pending jobs and approvals. Revoke compromised sessions including refresh families. Escalate `P1_AUDIT_CHAIN_FAILURE`; local logs are not an external paging service. Restore a protected database backup together with its encryption key in an isolated environment and verify the audit chains before resuming. Never use `docker compose down -v` or delete `.runtime` as a troubleshooting shortcut. Production alerting, key management, retention and incident ownership remain launch gates.
