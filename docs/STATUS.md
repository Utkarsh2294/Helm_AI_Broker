# Current build status

The [31 October assistant upgrade](ASSISTANT_GUIDE.md) implements source-stamped
streaming answers, private encrypted history, temporary local document extraction,
case evidence, PDF/DOCX exports, expiring authenticated compliance links and pinned
workspace/case panels. Light-only navigation and the two broker decisions remain.
The guide records the bounded local reasoning, unavailable structured fields and
browser/OCR requirements; no external LLM or Whisper service is connected.

[Assistant verification](verification/assistant-upgrade.json) records 576 passing
backend tests, affected security/evidence rechecks, nine frontend units, successful
desktop/mobile and Docker assistant journeys, and zero axe violations across four
assistant states. Local-preview and Docker APIs both serve the new response
version. Real image/scanned-PDF OCR, PostgreSQL revision 011 and append-only SQL
guards pass in Docker. Physical voice devices and independent acceptance remain
outside these automated checks.

The latest workspace simplification removes the agent-team page, team strip,
dark-mode controls/styles and combined audit page. Each case row opens its own
audit directly; existing evidence, agent execution and approval controls remain.
Retired team/audit links return to the dashboard.

[Workspace verification](verification/case-audit-workspace.json) records the web
and container builds, nine passing frontend units, the 14-scenario browser run
and four passing final rechecks after the mobile/link fixes. The local preview
and Docker site both pass case-scoped audit and light-only checks. Backend
regression was not repeated for these frontend-only changes.

The 31 October owner-requested automatic demo now has two human decision stages:
policy selection/order and authenticated final sign-off. Durable agent jobs handle
preparation and post-delivery evaluation; the case file, per-agent work/reasons,
readable audit and scoped local assistant are available from each case. See
[the walkthrough and control boundaries](TWO_DECISION_DEMO.md). Earlier manual
showcase evidence below refers to that separate flow.

[Automatic-demo verification](verification/agentic-demo.json) records 11 passing
new backend checks, nine frontend units, successful walkthroughs in the local
preview and Docker/CrewAI, and zero automated accessibility violations across
38 states. The broad runs found a missing test import and two accessibility
issues; the corrected backend suite and six affected browser journeys pass.
The full suites were not repeated after those targeted fixes. Existing live
launch blockers are unchanged.

The active specification is [the complete main plan](spec/HELM_BROKER_PORTAL_PROJECT_PLAN%20main.md), supplied on 30 October 2026. See [the main-plan phase ledger](phases/MAIN_PHASES.md) for current acceptance and [the baseline comparison](phases/MAIN_PLAN_BASELINE.md) for the gaps identified against the earlier build.

Main-plan P0–P9 are implemented for the fictional prototype, with the additional gaps tracked in [the full-plan audit](phases/FULL_PLAN_AUDIT.md). The earlier main-plan baseline passed **560 tests, including the 18 engine-package tests**, plus 7 frontend units, 16 independent JavaScript engine checks and the production web-server check. Its clean production-web browser run passed **31 tests**. Build, Ruff/ESLint/Prettier, Spectral contracts, SQLite/PostgreSQL migrations and immutable SQL evidence guards passed at that baseline. See [baseline regression](verification/demo-regression.json), [baseline browser run](verification/demo-browser.json) and [container workflow](verification/demo-container.json). Earlier phase reports are historical evidence, not additional tests to double-count.

The light theme stays readable under OS dark mode. Axe reports **zero violations across 25 checked screens/states**, including uploaded documents, all published case tabs, G2 review, referral/complaint holds, separate pilot reviews and mobile text resizing. [Accessibility evidence](verification/demo-accessibility.json) does not substitute for manual screen-reader/device acceptance. The earlier Lighthouse baseline remains 100/100/100; it is not relabelled as a new Lighthouse run. Exact load results and unmet targets remain in the performance reports.

The [follow-up load run](verification/demo-performance.json) verifies 50-client SSE event delivery at p95 126.49 ms, while retaining unmet queue and ranking-submit targets. P10 performance acceptance therefore remains partial.

The owner requested a **demo document flow to showcase how this works**. [Pilot showcase](DEMO_SHOWCASE.md) now provides seven labelled PDFs, consented source upload, the normal G0–G2 workflow, independent fictional compliance/legal reviews and a fingerprint-bound review-record PDF. The preview is prepared at `http://127.0.0.1:5180/demo`. The real consumer portal, insurers, paid models and email are not connected. Records, encryption keys and history are preserved; new commits use Garv Gupta.

The 31 October usability update lets a broker select a saved recommended plan while reviewing the others, preserves the other choices while editing one assessment, and shows saved/selected counts with a jump to the next unfinished plan. Final review now follows **Client needs → Selected plans and listed gaps → Final confirmation**. Approval appears after the current review is saved; no human confirmation is pre-checked. All five assessments and the unchanged server-side G2 checks remain required before publication. The previous regression reports describe their recorded revisions; follow-up workflow evidence is separate.

P10 live acceptance remains partial; P11's requested fictional review flow is complete while live release stays **NO GO**. CI API/web and Semgrep checks pass. Strict dependency/image scans still fail: the selected Trixie image has 44 high OS-package findings and four ChromaDB findings (two high, two critical), without listed fixes. Bookworm was tested and rejected because it increased OS findings to 59 high and two critical. [CI evidence](verification/demo-ci.json) retains the failed gates. Production secrets/KMS, external object lock/paging, representative model/OCR evaluation, staging performance/security/manual accessibility and named FCA/legal/DPO/compliance approval remain live requirements. Local write-once anchoring and [verified encrypted restore](verification/demo-recovery.json) are demonstrations, not external infrastructure acceptance.

Read [the launch checklist](launch-checklist.md), [DPIA draft](dpia/helm_broker_portal_dpia.md), [model card](model-cards/engine-v1.1.md) and [operator guide](runbooks/operator-guide.md) before connecting real data.
