# Workspace assistant, task copilot and Insights

Implements the [workspace master prompt](spec/WORKSPACE_ASSISTANT_MASTER_PROMPT.md).
The broker explicitly chose **local demo replies** on 2 November 2026. External
model calls remain disabled. The earlier light-only, per-case audit and two
human decisions requirements remain in force.

## Run and show the demo

1. Run `powershell -NoProfile -File scripts/start.ps1` from the repository.
   Use `-Install` on a new checkout to install the locked dependencies.
2. Open `http://127.0.0.1:5180` and sign in as `broker@helm.demo` with the
   existing fictional demo password `HelmDemo!2026`.
3. Choose **Review priority queue** in the banner. It clears earlier search/status/assignee/priority and aging filters, moves focus to **Your priority queue**, and shows open cases ordered by the deterministic task score. The button also works when you are already viewing that queue.
   **Tasks** opens the right rail on any authenticated page. Open a task to reach
   its case; **Why this matters** explains the saved state and cites its source.
   A snooze hides a task for one hour, retaining its outstanding state and reason.
4. Choose **Start automatic demo**. Agents prepare the fictional facts, quotes
   and ranking automatically. The broker chooses and orders three policies,
   then reviews and authenticates the final sign-off. No extra agent-run buttons
   or fabricated human ratings are introduced.
5. Open the bell to review your scoped notifications, or open the full inbox.
   Read/read-all, older pages, digest timezone and optional voice preferences are
   available there. Device push is requested only after **Enable browser
   notifications**. Payloads contain a generic reminder; case details require login.

## Ask Helm

- Use **Ask Helm**, the header **Assistant** button, or **Ctrl/Cmd K** from any
  authenticated page. The floating pill can be dragged on desktop and is centred
  near the bottom on phones. **Ctrl/Cmd Shift K** remains the case-search shortcut.
- Opening a case binds the assistant to that case and shows the client and saved
  workflow state. Ask about preferences, ranking, a named plan, agent work, the
  latest saved event or the next action. On Insights, period questions use the
  current URL filters. Missing facts and unavailable outcomes are stated explicitly.
- Replies stream over a POST response; questions do not enter URL query strings.
  The local engine retrieves saved evidence, rather than calling an external LLM.
  Confidence refers to those records and does not certify suitability.
- Numbered citation chips show source details and available snippets in a popover.
  They link to the appropriate accessible case view. The fixed statement under
  the composer explains that the assistant cannot select policies or approve advice.
- **History** searches the recent browser-held conversation. **Clear conversation**
  asks for confirmation. Login changes invalidate the browser history; logout clears
  it. The server records immutable query/response hashes, broker, case and timestamp.
  Full replies are retained when explicitly saved as evidence or shared for review;
  older, already-retained evidence is not destroyed by clearing chat.

## Files and voice

- Attach or drop PDF, DOCX, XLS/XLSX, CSV, PNG/JPG/WebP/TIFF, UTF-8 text/Markdown/
  JSON, or MP3/WAV/M4A/WebM. Limits: five files, 25 MB per file, 50,000 extracted
  characters per file and 150,000 combined. Preview, page count when available,
  truncation and duplicate status are shown. Office macros and formulas never run.
- PDF extraction uses PyMuPDF, images/scanned pages use local Tesseract English,
  spreadsheets use bounded local parsers. PDFs are capped at 50 pages, scanned
  PDFs/images at five pages. Temporary encrypted extracts expire with the login
  or after one hour. SHA-256 caching is bound to broker, login, case and format;
  the original uploaded file is not retained.
- Case document analysis uses the existing verified medical-access permission.
  Uploaded prose is treated as potentially sensitive and never becomes an agent
  instruction or an automatic update to the client's preferences.
- **Voice input** uses browser speech recognition with interim English transcripts
  and a 2.5-second silence timeout. Browser speech may use the browser vendor's
  service. When unavailable due to a service error or unsupported browser,
  MediaRecorder records up to 60 seconds for **local Whisper** transcription.
  Review the transcript, then send it yourself. Audio is not retained.
- Prepare public model weights once with
  `C:\Users\rajut\AppData\Local\HelmBroker\venv\Scripts\python.exe tools/prepare_speech.py`.
  The default model is CPU `base.en`; requests do not download weights or send
  audio to a provider. For another checkout use its configured Python executable.
  Docker needs these weights in the shared `/app/.runtime/whisper/base.en` directory.
- Read-aloud supports pause, resume, stop and 0.75–1.5× speed. Voice and microphone
  permissions remain browser/device dependent. Chat limits are 30 queries/minute
  per broker; transcription is limited to five requests/minute.

## Supporting research

1. **Save to evidence** pins the server-authenticated answer and sources to the
   current case. Workspace replies open a searchable case picker. A reply that
   cites another case or summarises multiple cases cannot be moved into that file.
2. **Evidence** lists the case's supporting research. **Remove** hides research
   from the working list with a five-second **Undo** toast. Immutable snapshots
   and the per-case audit remain available.
3. The recommendation displays **Supporting research**, and **Download
   recommendation PDF** includes the research appendix for that pack version.
   Updating research in an unsigned draft creates a new pack hash and invalidates
   previous review confirmations. Published packs retain their signed version.
4. PDF/DOCX export includes the displayed answers, stamps and citations.
   **Share for compliance** creates a 24-hour link requiring a compliance login
   and the reviewer's own case/medical access. The app does not send the link.

## Broker Insights

The separate **Broker insights** page provides URL-backed date, coverage,
insurer and permitted broker filters; KPI trends; intake volume; clickable case
aging; completion/state durations; provider choice funnel; satisfaction;
requested coverage/budget patterns; renewal cohorts; anomaly signals; PDF/CSV
scorecards; and a three-sentence local period summary.

Plain brokers receive their own/unassigned projections. Comparing another broker
or viewing productivity requires senior/admin or the existing lead-broker authority,
enforced by the server. Consumer satisfaction comes only from signed Core survey
events, not policy rating stars. Renewal retention requires a hashed stable consumer
reference, explicit source-case link and confirmed binding. Unsupported benchmarks,
missing outcomes and insufficient regression samples remain unavailable.

PostgreSQL's daily materialized view refreshes every 15 minutes. Other indexed
operational aggregates use a five-minute scope-bound Redis cache, invalidated after
source commits. The worker generates local-time digests, SLA warnings and nightly
descriptive satisfaction/aging signals. `tools/refresh_insights.py` runs the same
jobs manually. Demo SLA values are operational configuration, not regulatory claims.

## Verification

See [the implementation and acceptance record](verification/WORKSPACE_ASSISTANT_2026-11-02.md)
for actual checks, measured performance, configuration boundaries and remaining
acceptance limits. Run `tools/benchmark_workspace.py` only with the local demo
PostgreSQL/Redis services: it creates a separate synthetic 100,000-case database.
