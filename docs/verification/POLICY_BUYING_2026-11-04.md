# Policy Buying acceptance — 4 November 2026

PB-0 through PB-6 are implemented as a local demonstration against
[the supplied specification](../spec/HELM_POLICY_BUYING_WORKFLOW.md).
The [operating guide](../POLICY_BUYING_GUIDE.md) explains both underwriting paths,
the broker decisions and the deliberate simulation boundaries.

The supplied file was preserved unchanged. Its SHA-256 is
`BAB30BD326CD440F30A3BFD10C319F52263C3365D8BAE9624CC72FE4C1C8C9A2`.

## Delivered phases

| Phase | Delivered behaviour | Acceptance evidence |
|---|---|---|
| PB-0 | Separate buying pipeline, explicit published-quote selection, eight-stage workspace, saved updates, priorities, Task Copilot and case assistant | Selection/permissions/concurrency tests; desktop and phone browser journeys; priority navigation checks |
| PB-1 | Original underwriting baseline, ten-section IPID, versioned review, basic formatting, local targeted rewriting, PDF and consumer correction loop | Template, revision, stale-confirmation and PDF checks; actual generated two-page PDF visually inspected |
| PB-2 | Independently reviewed TOBA, consumer acknowledgement and stable-consumer standing acceptance | Version/content-bound acceptance tests; both browser journeys |
| PB-3 | Protected Moratorium declaration, blank FMU questionnaire, fresh fictional answers, restricted medical review and broker underwriting approval | Both complete branches; medical-access and isolation tests |
| PB-4 | Automatic fictional banking request, encrypted response, masking, authenticated one-time reveal and explicit broker verification | Reveal/replay/permission tests; browser verification; delayed-refresh UI regression test |
| PB-5 | Accepted-version package, non-medical cover note, final read-only review and idempotent mock insurer handoff | Stale-package and duplicate-send tests; both browser journeys |
| PB-6 | Immediate fictional issuance, green closed case, fake policy number, saved confirmation message and final IPID | Persisted closure/outbox tests and Docker browser journeys |

## Measured checks

| Check | Result |
|---|---|
| Full Python API and engine regression, including CrewAI framework execution | **614 passed**, 66 warnings, 460.21 seconds |
| Frontend unit suite | **12 passed** across five files |
| Both buying branches on PostgreSQL QA | **2 passed**; Moratorium and FMU through issuance |
| Priority queue desktop/phone checks | **2 passed**; buying cases open their buying workspace |
| Existing automatic demo and Copilot Insights browser regressions | **3 passed** |
| Both buying branches against the Docker prototype | **2 passed**; repeats the buying journeys on the deployed local stack |
| Final refreshed-prototype smoke check | Passed: API/Redis health, persisted issued case, precise document focus and case-scoped assistant |
| JavaScript engine checks | **16 passed** |
| Web server check | **1 passed** |
| Ruff lint/format, ESLint, Prettier and existing API contract lint | Passed |
| Production frontend and refreshed Docker images | Built successfully |
| Database | PostgreSQL upgraded to migration 021; SQLite upgrade/empty downgrade/re-upgrade and populated-evidence guards passed |
| Document rendering | Actual downloaded IPID has two pages; both inspected visually and both carry the demo watermark |

The buying browser tests include 1440-pixel desktop and 390-pixel phone layouts,
keyboard focus, horizontal-overflow assertions, browser-error capture and automated
WCAG A/AA checks. The sampled views had no reported axe violations. This is not a
claim of complete accessibility certification or physical-device coverage.

The final source refresh reused the already installed, locked Docker dependency
image, copied current application sources, and rebuilt the web image. It did not
repeat every package download. API, worker and both simulators use the refreshed
source image. Existing data volumes were retained. The checked-in Dockerfile and
lockfile remain the clean-build path.

Detailed local logs, screenshots and rendered PDFs are under the ignored
`.runtime/qa/` directory. They are local verification artifacts, not repository
fixtures. Representative logs are `pb-regression-final.log`,
`pb-web-unit-final.log`, `pb-js-engine.log`, `pb-web-server.log`,
`pb-contracts.log`, `pb-api-image.log` and `pb-web-image.log`.

## Important implementation decisions

- Buying uses separate persisted stages. The original recommendation's two broker
  decisions remain; the new buying approvals are those requested by this workflow.
- All selections and approvals bind to current versions. Document revisions reset
  affected confirmations and package readiness. Repeat final sends return the
  original issuance. Case permissions and complaint holds apply to mutations.
- Append-only encrypted document versions, medical responses, updates and standing
  agreements retain evidence. Empty-table migration rollback is allowed; populated
  evidence cannot be silently discarded.
- Approval feed ordering follows the actual human decision before the automatic
  action it triggers. Banking verification waits for the refreshed case version
  before enabling the next action.
- Deep links focus the requested document or review step. The case assistant
  receives buying progress without completed medical answers or raw bank details.

## Demonstration boundaries and remaining production work

The user chose local demo replies. Document rewriting therefore supports explicit
section replacement with basic bold/italic formatting; unrestricted model-generated
rewrites are not enabled. Unsupported instructions explain that limit without
changing a draft. The update panel displays the most recent 100 saved entries;
the per-case audit retains its separate evidence view.

Consumer actions are broker-authenticated simulation controls. Signatures,
questionnaire responses, banking values, insurer issuance and confirmation emails
are fictional. The confirmation is a local outbox record. No real payment,
external email, real consumer integration or live insurer connection was exercised.

Medical answers and banking use the existing authenticated AES-256-GCM storage.
Medical review needs consent and the session-bound medical grant. Raw banking is
revealed once with fresh authentication, then hidden. These values are excluded
from assistant context, general feed text and generic document exports.

Generated documents are illustrative and watermarked. Missing quote benefit
amounts remain explicitly missing. Real insurer wording, legal approval, firm
authorisation, electronic signatures and live integration arrangements remain
production work. Official reference-check limitations are recorded in the guide.

Existing dependency warnings remain in the Python suite. The frontend build also
reports its existing large-chunk and dependency annotation warnings. Checks pass;
this record does not describe the build as warning-free.
Final formatting also normalised four existing mock-core fixture expressions;
this changed spacing and quote style only.

## Delivery identity

The user verified GitHub account **GarvGupta25** and authorised continuation after
the corrected first checkpoint. This delivery uses **Garv Gupta** as author and
committer, with `226145193+GarvGupta25@users.noreply.github.com`. Checkpoints are
substantive capabilities and subsequent acceptance fixes, exceeding the requested
30 commits. The final push and remote attribution are verified separately at
delivery time.
