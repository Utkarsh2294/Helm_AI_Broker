# Helm saved-record assistants

Implemented against the [31 October master prompts](spec/HELM_ASSISTANT_MASTER_PROMPTS.md).
The broker's later workspace instructions remain in force: light mode only, no
team page/strip and no combined audit page. The five workflow agents and the two
automatic-demo broker decisions are unchanged.

## Open and ask

1. Sign in and click **Workspace assistant** on the dashboard for the inline view.
   The header **Assistant** button or **Ctrl/Cmd K** opens a pinned panel from any
   signed-in screen. Case search remains available on **Ctrl/Cmd Shift K**.
2. In a case, choose **Case assistant**. Its answers and history concern that case.
   **Pin panel** keeps it open beside the case journey, file or audit. Escape closes
   the pinned panel before closing the underlying case.
3. Choose a quick question or type one. Answers stream from saved local records,
   show numbered source references, three follow-up questions, confidence,
   broker ID, timestamp and `helm-local-evidence-v2`. Click a citation to inspect
   its source; source buttons open the relevant case/file/audit view.
4. Ask about preferences, a named policy, ranking criteria, saved agent work,
   documents, suitability gaps, evidence or the next step. Workspace questions
   cover counts, stale cases, blocked cases, status filters, client names and
   priority triage. Missing structured fields are reported rather than inferred.

## History, files and voice

- **History** searches the last 20 saved queries in the current scope for the
  signed-in broker. Expand a saved answer or click its question to ask it again.
  Follow-ups use up to ten recent turns from the same login session and case.
  This is bounded topic continuity, not unrestricted model conversation memory.
- **Attach files** or drop PDF, DOCX, XLSX, CSV, PNG/JPG/WebP or UTF-8 text into
  the assistant. Up to five files, 20 MB each. Receipt and parsing are confirmed.
  PDFs use local PyMuPDF; Office files use bounded ZIP/XML extraction; CSV uses
  the standard library. No Office macro, formula or document instruction runs.
- Images and scanned PDFs use local Tesseract with English data. The Docker image
  installs it. A Windows operator can install Tesseract and put it on PATH; restart
  the API afterwards. Without it, OCR returns a clear unavailable message. PDFs
  are limited to 50 pages, scanned PDFs to five; tables sample 200 rows and text
  extraction caps at 60,000 characters. Answers quote up to 2,000 characters per
  attachment, label the extract unverified and flag a detected budget conflict.
  This is extraction and a bounded comparison, not general semantic document QA.
- Case analysis and **Attach extract to case** require the existing verified
  medical access, authorised role and consent. Workspace attachments can be
  attached explicitly to a chosen accessible case after that verification. The
  saved extract appears in the digital file and protected document download.
  No preference, policy choice or fact-find field changes automatically. Confirm
  corrections through the existing fact-find review controls.
- Temporary extracted text is encrypted and bound to the login session, uploader
  and case, expires within one hour (or sooner when the login expires), and is
  excluded after expiry. Expired temporary rows are purged on the next upload.
  Original file bytes are discarded. Attaching an extract or saving an answer
  explicitly retains that evidence; submitted questions and answer extracts are
  retained in encrypted audit history.
- **Voice input** uses supported browsers' speech recognition in British English.
  The browser may use its own speech service. Review the transcript before Send;
  transcription never auto-submits a question. Unsupported/denied microphones
  leave typing available. **Read aloud** uses browser speech synthesis, with the
  preference stored per broker on that browser. **Listen** reads one answer.
  No external Whisper or speech-provider credentials are configured or invoked.

## Evidence, export and compliance review

1. **Copy** copies the answer text. **Save to evidence** pins an immutable answer,
   response stamp and source snapshot to the current case; the evidence badge
   increments and repeat saves do not duplicate it.
2. **Evidence** lists the saved answers. Case **Download evidence** includes the
   assistant appendix in JSON/PDF. Protected document analysis is redacted from
   the ordinary bundle and requires the existing medical-access export option.
3. **PDF** or **DOCX** downloads the current displayed response thread, with
   numbered references and audit stamps. Only the querying broker can export
   their private assistant history through these controls.
4. **Share for compliance** creates a 24-hour read-only link to one saved response.
   Send it through your normal approved channel. A compliance officer must sign
   in; possession of the URL alone grants no access. Expired links fail and
   protected analysis additionally requires the reviewer's own medical access.
5. The per-case audit records explicit evidence saves, document attachment and
   review-link creation. Every response is separately retained in encrypted,
   append-only `assistant_logs`, with broker, case, model version and timestamp.

## Deliberate boundaries

The assistant is a deterministic local saved-evidence companion, with no external
LLM, web search, insurer access, premium refresh, policy selection, approval or
consumer-link delivery. Upload content is data, not an instruction to the agents.
Confidence describes saved-record retrieval, not a suitability or legal verdict.
ICOBS 5/6/7 topic flags are prompts for the broker's approved compliance review;
they are not live regulatory-text verification or a compliance certification.

The existing ranking has affordability, coverage, network, underwriting, insurer
quality, process ease and terms clarity. Answers use its actual saved weights,
utilities and 70% WSM / 30% fixed-anchor TOPSIS blend. They do not invent separate
claims-speed or dental/optical criteria. Current individual/couple/family profiles
do not have structured employer census bands, renewal dates or current-insurer
fields, so those filters explicitly report the gap. Agent names and output history
reflect the actual five-agent implementation, rather than inventing a sixth role.

## Deployment

Apply Alembic revision `011` before starting the updated API/worker. The ordinary
start script and Compose API command already run `alembic upgrade head`. No data
reset is needed. The assistant upload route alone has a 29 MB JSON request cap
for base64 encoding a 20 MB file; other routes retain their 2 MB cap. Speech needs
localhost or HTTPS and the user's browser permission. Microphone permissions are
restricted to the same origin. API contracts include the assistant routes.

See [verification evidence](verification/assistant-upgrade.json) for exact runs
and remaining device checks.
