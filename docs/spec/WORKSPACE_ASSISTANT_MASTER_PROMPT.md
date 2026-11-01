# Workspace Assistant — Master Prompt

Phase **WA** · Stack: React 18 + Vite + JSX (no TypeScript on website) · Python 3.12 + FastAPI · PostgreSQL 16

---

## 1. Overview & Purpose

The Workspace Assistant is a persistent AI-powered chat panel embedded in every page of the Helm broker portal. It is context-aware, document-reading, and voice-enabled — helping brokers work faster without bypassing compliance gates.

Key capabilities:

- Answer questions about any open case, shortlisted plans, insurer terms, or FCA rules
- Accept voice input (browser mic) and transcribe spoken questions to text
- Read uploaded documents of any type — PDF, images, Word, Excel, CSV, audio — and answer questions about them
- Stream answers token-by-token as they form
- Save answers as **Saved Evidence** attached to a case record
- Open instantly via **Cmd+K** or a floating pill in every page corner
- Cite the exact case record, document section, or plan an answer draws from

Critical compliance constraints (hard-coded in server logic, NOT in LLM prompts):

- The assistant **cannot select policies** on the broker's behalf
- The assistant **cannot approve advice** or trigger the publish gate
- The assistant **cannot access medical data** without step-up authentication
- Every query is written to the audit log with query hash, broker ID, and timestamp
- The subtitle "This assistant cannot select policies or approve advice" is always visible below the input

---

## 2. Full Tech Stack

**Frontend (React 18 + Vite, JSX only — no TypeScript on website)**

- react 18, react-dom 18, vite 5
- framer-motion 11 — panel spring animations, typewriter token render
- @radix-ui/react-\* — dialog, popover, scroll-area, tooltip (accessible primitives)
- sonner — toast notifications (copy confirmed, evidence saved)
- @tanstack/react-query v5 — evidence list, suggestions caching
- Web Speech API (SpeechRecognition) — browser-native mic input
- MediaRecorder API — audio capture for Whisper fallback
- EventSource — SSE token streaming from FastAPI
- @use-gesture/react — drag-to-dismiss panel on mobile

**Backend (Python 3.12 + FastAPI — no language restrictions)**

- fastapi 0.115 + uvicorn\[standard\]
- pdfplumber — PDF text and table extraction; pytesseract + Pillow fallback for scanned PDFs
- python-docx — Word document (.docx) paragraph and table extraction
- openpyxl — Excel (.xlsx / .xls), all sheets, auto header detection
- openai-whisper (model base.en) — server-side audio transcription (MP3, WAV, M4A, WebM/Opus)
- litellm — LLM gateway with PII redaction wrapper (strips NHS numbers, NI numbers, postcodes before sending to model)
- sqlalchemy 2.0 async + asyncpg — async PostgreSQL 16
- arq + redis — background job queue for large document parsing
- pydantic v2 — request/response validation

**Database tables (PostgreSQL 16)**

- assistant\_audit — every query logged: broker\_id, query\_hash, response\_hash, timestamp, case\_id
- file\_parses — parsed file content cached by SHA-256 of file bytes (re-upload de-duped)
- case\_evidence — broker-saved assistant answers attached to a specific case

---

## 3. Voice & Mic Input

### 3.1 Web Speech API (Primary — browser-native, zero latency)

Use the browser SpeechRecognition / webkitSpeechRecognition API. Configure:

- lang: 'en-GB' (UK English for broker terminology: "IPID", "moratorium", "BUPA")
- continuous: false (single utterance mode)
- interimResults: true (shows real-time transcript preview as broker speaks)
- Auto-stop after 2.5 seconds of silence (use speechend + 2500ms timeout)

On result: fill the input field with the final transcript. On error: fall back to Whisper.

**Hook: useSpeechInput()**

```
const useSpeechInput = (onTranscript) => {
  const [state, setState] = useState('idle'); // idle | listening | processing | error
  const recognitionRef = useRef(null);
  const start = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { startWhisper(); return; }
    const r = new SR();
    r.lang = 'en-GB';
    r.interimResults = true;
    r.onresult = (e) => {
      const t = Array.from(e.results).map(r => r[0].transcript).join('');
      onTranscript(t, e.results[e.results.length-1].isFinal);
    };
    r.onend = () => setState('idle');
    r.onerror = () => startWhisper();
    recognitionRef.current = r;
    r.start();
    setState('listening');
  };
  return { state, start, stop: () => recognitionRef.current?.stop() };
};
```

### 3.2 Whisper Fallback (Server-side, Firefox + mobile)

When SpeechRecognition is not available or returns an error:

1. Start MediaRecorder with mimeType 'audio/webm;codecs=opus'
2. Record until broker clicks stop (or 60s hard limit)
3. POST audio blob to /assistant/transcribe as multipart/form-data with field name 'audio'
4. Backend: `openai-whisper` load model 'base.en', transcribe, return JSON: {text, duration\_s, language}
5. Fill input field with returned text

**Backend endpoint (Python/FastAPI):**

```
@router.post('/assistant/transcribe')
async def transcribe_audio(audio: UploadFile, broker=Depends(require_broker)):
    import whisper, tempfile, os
    model = whisper.load_model('base.en')
    with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as f:
        f.write(await audio.read()); tmp = f.name
    result = model.transcribe(tmp, language='en', fp16=False)
    os.unlink(tmp)
    return {'text': result['text'].strip(), 'language': result['language']}
```

### 3.3 UI States for Mic Button

- idle: mic icon, grey, tooltip 'Start voice input'
- listening: red pulsing dot + animated waveform bars, label 'Listening...', click to stop
- processing: spinner + 'Transcribing...' (shown during Whisper call only)
- error: amber icon, tooltip 'Mic not available — try typing'

All state transitions animated with Framer Motion (spring: stiffness 400, damping 28).

---

## 4. File Upload & Multi-Format Parsing

### 4.1 Supported Formats

| Format | Extension(s) | Parser (Python) | Notes |
| --- | --- | --- | --- |
| PDF | .pdf | pdfplumber; pytesseract fallback for scanned pages | Extracts text + tables; page count returned |
| Image | .png .jpg .jpeg .webp .tiff | Pillow pre-process + pytesseract OCR | Auto-deskew, threshold, then OCR |
| Word | .docx | python-docx | Paragraphs + inline tables; headers/footers included |
| Excel | .xlsx .xls | openpyxl | All sheets; auto-detects header row; converts to markdown table |
| CSV | .csv | csv stdlib | Auto-detects delimiter (comma, semicolon, tab); first 200 rows |
| Text | .txt .md | utf-8 decode | Full content up to 50k chars |
| JSON | .json | json stdlib | Pretty-printed; truncated at 50k chars |
| Audio | .mp3 .wav .m4a .webm | openai-whisper base.en | Full transcription returned as text |

### 4.2 Upload & Parse Flow

1. Broker drags a file onto the input area OR clicks the paperclip icon
2. Client validates file size (max 25 MB) and type (allowed extensions list); reject with inline error if invalid
3. Client sends file via POST /assistant/parse as multipart/form-data with fields: file, case\_id (optional)
4. Backend reads file bytes, hashes with SHA-256, checks file\_parses cache (skip re-parse if already stored)
5. Backend selects correct parser from PARSER\_MAP keyed by extension
6. Parser returns: {file\_id, filename, page\_count, char\_count, preview (first 500 chars), content (full text)}
7. Backend saves row to file\_parses table; returns {file\_id, filename, preview, page\_count} to client (NOT full content)
8. Client displays a FileChip in the input toolbar: filename, page count, X to remove
9. On send, client includes file\_ids list; backend fetches full content from file\_parses by file\_id and injects into LLM system prompt as \[DOCUMENT: filename\]\\ncontent

### 4.3 Backend Parse Endpoint

```
@router.post('/assistant/parse')
async def parse_file(file: UploadFile, case_id: str = None, broker=Depends(require_broker)):
    data = await file.read()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(413, 'File too large (max 25 MB)')
    sha = hashlib.sha256(data).hexdigest()
    cached = await db.fetchrow('SELECT * FROM file_parses WHERE sha256=$1', sha)
    if cached:
        return {'file_id': cached['id'], 'filename': file.filename,
                'preview': cached['content'][:500], 'page_count': cached['page_count']}
    ext = Path(file.filename).suffix.lower()
    content, page_count = await PARSER_MAP[ext](data, file.filename)
    content = content[:50000]  # hard cap
    file_id = await db.fetchval(
        'INSERT INTO file_parses(sha256,filename,content,page_count,broker_id) VALUES($1,$2,$3,$4,$5) RETURNING id',
        sha, file.filename, content, page_count, broker.id)
    return {'file_id': str(file_id), 'filename': file.filename,
            'preview': content[:500], 'page_count': page_count}
```

### 4.4 File Size & Content Limits

- Max file size: 25 MB per file
- Max files per message: 5
- Max content length per file: 50,000 characters (truncated with \[content truncated at 50,000 chars\] appended)
- Total injected context per message: 150,000 characters across all files combined

---

## 5. Streaming LLM Responses (SSE)

### 5.1 FastAPI SSE Endpoint

```
from fastapi.responses import StreamingResponse
import json, asyncio

@router.get('/assistant/chat')
async def chat_sse(
    message: str, case_id: str = None, file_ids: str = '',
    broker=Depends(require_broker)
):
    # 1. Build system context (see Section 9)
    system_ctx = await build_system_context(broker, case_id)
    # 2. Fetch file contents
    docs = await fetch_file_contents(file_ids.split(',') if file_ids else [])
    # 3. Medical firewall: strip medical fields from context
    system_ctx = medical_firewall_scrub(system_ctx)
    # 4. Build messages array
    messages = [
        {'role': 'system', 'content': WORKSPACE_ASSISTANT_SYSTEM_PROMPT + system_ctx + docs},
        {'role': 'user', 'content': message}
    ]
    # 5. Audit log entry
    audit_id = await log_assistant_query(broker.id, case_id, message)
    # 6. Stream via litellm
    async def generate():
        full_response = ''
        async for chunk in await litellm.acompletion(
            model='gpt-4o', messages=messages, stream=True,
            metadata={'pii_redact': True}
        ):
            token = chunk.choices[0].delta.content or ''
            full_response += token
            yield f'data: {json.dumps({"token": token, "done": False})}\n\n'
        citations = extract_citations(full_response)
        await log_assistant_response(audit_id, full_response)
        yield f'data: {json.dumps({"done": True, "citations": citations, "audit_id": str(audit_id)})}\n\n'
    return StreamingResponse(generate(), media_type='text/event-stream',
                             headers={'X-Accel-Buffering': 'no', 'Cache-Control': 'no-cache'})
```

### 5.2 React EventSource Hook

```
const useAssistantChat = (caseId) => {
  const [messages, setMessages] = useState([]);
  const [streaming, setStreaming] = useState(false);
  const send = async (text, fileIds = []) => {
    setStreaming(true);
    const assistantMsg = { id: uuid(), role: 'assistant', content: '', citations: [] };
    setMessages(prev => [...prev,
      { id: uuid(), role: 'user', content: text, fileIds },
      assistantMsg
    ]);
    const params = new URLSearchParams({ message: text, case_id: caseId || '', file_ids: fileIds.join(',') });
    const es = new EventSource('/api/assistant/chat?' + params);
    es.onmessage = (e) => {
      const { token, done, citations, audit_id } = JSON.parse(e.data);
      if (done) {
        setMessages(prev => prev.map(m =>
          m.id === assistantMsg.id ? { ...m, citations, audit_id } : m));
        setStreaming(false); es.close(); return;
      }
      setMessages(prev => prev.map(m =>
        m.id === assistantMsg.id ? { ...m, content: m.content + token } : m));
    };
    es.onerror = () => { setStreaming(false); es.close(); };
  };
  return { messages, streaming, send };
};
```

### 5.3 Token Render (Framer Motion Typewriter)

Each new token appended to message content triggers a React re-render. Wrap the content area in a motion.span with layout='position' to prevent layout shifts. The streaming cursor is an animated blinking underscore that disappears when done: true is received.

---

## 6. Saved Evidence Feature

### 6.1 Purpose

When the assistant gives a useful answer (e.g. "Plan B1 has a 3-day turnaround vs Plan A2's 7-day turnaround"), the broker can save that exchange as evidence attached to the case. This evidence surfaces in the Suitability Review and the Audit Trail, giving regulators a clear record of AI-assisted research that the broker reviewed.

### 6.2 Save-to-Case Flow

1. Each assistant message has a 'Save to Case' button (bookmark icon) in its action bar
2. Broker clicks 'Save to Case' — if no case is in context, a case-picker popover opens
3. POST /assistant/evidence with: {response\_id, case\_id, query, response\_text, citations, file\_ids}
4. Row saved to case\_evidence table
5. Saved Evidence badge in top-right panel header increments its count
6. Toast: 'Saved to Case #1234'

### 6.3 Database Schema

```sql
CREATE TABLE case_evidence (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id     UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    broker_id   UUID NOT NULL REFERENCES brokers(id),
    audit_id    UUID REFERENCES assistant_audit(id),
    query       TEXT NOT NULL,
    response    TEXT NOT NULL,
    citations   JSONB DEFAULT '[]',
    file_ids    UUID[] DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_case_evidence_case ON case_evidence(case_id);
```

### 6.4 Saved Evidence Panel

The 'SAVED EVIDENCE' badge in the assistant panel header opens a collapsible side-panel listing all saved evidence for the current case. Each item shows:

- Query text (truncated to 80 chars)
- Response preview (first 150 chars)
- Timestamp
- Attached file names (if any)
- 'View full' to expand in a dialog
- 'Remove' to delete (with undo toast, 5-second window)

Evidence items are displayed in the Suitability Review screen under 'Supporting Research' and are appended to the Advice Record PDF export.

---

## 7. Modern UI Features

### 7.1 Cmd+K / Ctrl+K Global Quick Open

Register a global keydown listener in the root App.jsx. When Cmd+K (Mac) or Ctrl+K (Windows/Linux) is pressed and the assistant is not already open, animate it open from the bottom-right corner. If a case page is active, pre-fill context. Use Framer Motion spring (type: 'spring', stiffness: 380, damping: 30) for the expand animation.

### 7.2 Floating Pill (Minimised State)

When the assistant is closed, a small pill anchored bottom-right shows: chat bubble icon + 'Ask' label. If there are unread proactive messages (e.g. auto-generated case summary when broker opens a case), show an orange dot badge. Click to expand. Drag to reposition (persisted in localStorage). On mobile, pill is fixed at bottom-center.

### 7.3 Citation Cards

When the LLM response references a specific source, the citation is extracted client-side from the response text using regex patterns for \[Case #NNN\], \[Plan ID: XXX\], \[Document: filename, p.N\]. Each citation renders as an inline chip with:

- Source type icon (case, plan, document)
- Short label ('Case #1234, DNR Draft')
- Click expands a popover with the referenced snippet
- Deep link to the relevant section of the case when applicable

### 7.4 Text-to-Speech Read-Aloud

Each completed assistant response has a speaker icon in its action bar. Click to read the response aloud using browser speechSynthesis API with voice 'en-GB' (falls back to any English voice). Controls appear inline: pause/resume button, speed selector (0.75x / 1x / 1.5x). Reading progress shown with a thin animated underline sweeping through the text. Stops automatically when broker opens a new message.

### 7.5 Suggested Quick-Action Prompts

When the input is empty, show a row of contextual prompt chips below the text field:

- On any case page: 'Summarise this case', 'What are the open blockers?', 'Compare top 3 plans', 'Check suitability criteria'
- On queue page: 'Show overdue cases', 'Summarise new cases today', 'Which cases need action?'
- On insights page: 'Explain the NDCG score', 'How is the recommendation model performing?'

Chips are hidden the moment the broker starts typing. Pressing a chip fills the input and sends immediately.

### 7.6 Copy to Clipboard

Each assistant response has a copy icon (document-duplicate). Click copies the full response text to clipboard. A 'Copied!' toast appears for 2 seconds. The icon briefly changes to a checkmark.

### 7.7 Conversation History (Per-Session)

The last 20 messages are persisted in localStorage under key helm\_assistant\_history\_{brokerId}. On assistant open, history is rehydrated. 'Clear chat' button in the header wipes history with a confirmation dialog. Conversation history is session-specific and is NOT shared across devices or persisted server-side.

### 7.8 Dark Mode, Reduced Motion & Accessibility

- All colours use CSS variables from the Helm design token system (--color-surface-*, --color-text-*, etc.)
- Respects prefers-color-scheme: dark automatically
- Respects prefers-reduced-motion: all Framer Motion animations disabled; instant transitions
- All interactive elements have visible focus rings (2px outline, --color-focus)
- ARIA labels on mic button, file upload, and all action icons
- Screen reader announces 'Assistant is typing...' during streaming, 'Response ready' on completion

---

## 8. Context Awareness & Case Integration

### 8.1 System Context Injected into Every Chat Request

The backend builds this context block and prepends it to the LLM system prompt:

```
BROKER CONTEXT:
- Broker: {broker.full_name} ({broker.email}), Role: {broker.role}
- Current case: {case.reference} | {consumer.name} | State: {case.state} | Created: {case.created_at.date()}
- Case type: {case.coverage_type} | Budget: GBP {case.budget_annual_pence/100:.0f} p.a.
- Shortlisted plans: {', '.join([p.id + ' (' + p.insurer_name + ')' for p in shortlisted_plans])}
- Ranked plans (top 3): {', '.join([r.plan_id + ' score=' + str(r.score) for r in top3])}
- Open halt reasons: {', '.join(case.halt_reasons) or 'none'}
- Outstanding blockers: {', '.join(case.blockers) or 'none'}
- Today: {today_date} | Clock: {clock_type}

You are the Workspace Assistant for Helm broker portal. Help the broker understand this case, the recommended plans, FCA rules, and insurer terms. Do NOT select plans, approve advice, or access medical data. Keep responses concise and cite the source (case field, plan criterion, regulation) for every claim.
```

### 8.2 'Summarise My Workspace' Button

When broker clicks this button (visible on queue page and when no case is in context):

- POST to /assistant/chat with message 'Summarise my workspace' and no case\_id
- Backend fetches broker's active cases (states not in CLOSED/PUBLISHED/DECLINED) and injects a workspace summary:
  - Total active cases, breakdown by state
  - Cases awaiting broker action (AWAITING\_BROKER\_REVIEW)
  - Cases halted (PAUSED\_NEEDS\_HUMAN) with halt reason
  - Cases overdue (created > 5 business days ago, not published)
- LLM generates a plain-language summary in under 200 words
- Result cached for 5 minutes (redis key: workspace\_summary:{broker\_id})

### 8.3 Case-Scoped Mode

When the assistant is opened from inside a specific case page:

- case\_id is automatically passed to all chat requests
- Assistant header shows 'Case #NNNN — {consumer.name}' as subtitle
- Suggested prompts are specific to that case's state
- File uploads are automatically associated with that case
- Saved Evidence automatically attaches to that case without showing the case picker

### 8.4 Real-Time State Awareness

If the case state changes while the assistant is open (detected via SSE case\_state\_updated event), the system context is automatically refreshed. If the broker asks 'What just happened?' after a state change, the assistant describes the transition using the audit event payload.

---

## 9. Compliance Rails (Hard-Coded in Server — NOT LLM Prompts)

| Rule | Where enforced | Detail |
| --- | --- | --- |
| Cannot select policies | POST /cases/:id/select requires broker JWT + G2 step-up; assistant JWT never has select scope | 403 if assistant token attempts this endpoint |
| Cannot approve advice | POST /cases/:id/publish requires step-up auth + broker\_id in body + G2 gate check | Assistant has no path to this endpoint |
| Medical data firewall | medical\_firewall\_scrub() strips all fields matching MF1-MF10 rules before LLM injection | Logs MF\_SCRUB event to audit |
| PII redaction | LiteLLM PII wrapper strips NHS numbers (\\bNHS\[- \]?\\d{3}\[- \]?\\d{3}\[- \]?\\d{4}\\b), NI numbers, full postcodes before sending to external model | Applies to both prompt and response logging |
| All queries audited | Every /assistant/chat call writes to assistant\_audit before streaming begins | audit\_id returned in final SSE event |
| Rate limiting | 30 requests/minute per broker on /assistant/chat; 5 transcription requests/minute | Returns 429 with Retry-After header |
| Subtitle always visible | AssistantHeader component renders the subtitle as a static div outside the chat area; cannot be hidden by broker | Part of the non-configurable shell |
| No cross-case data | Context injection filters to current case only; broker cannot ask about another broker's case | Backend filters by broker\_id at query time |

---

## 10. Live Guided Task Copilot (Visual Bot) & Real-Time Notifications

### 10.1 Purpose

Beyond the Q&A chat assistant (Sections 1–9), the portal gets a second, always-on presence: a **visual guide bot** that proactively tells each broker what is left to do, where to click, and why — plus a **real-time notification layer** that surfaces new and pending work the moment it happens, without the broker needing to ask.

This is NOT a chat window the broker types into. It is a **proactive, visual, clickable** companion: task cards with deep links, a notification bell with live badges, a priority banner on login, and an "Explain this case" panel that teaches the broker what their job is on that specific case and how to do it well.

### 10.2 Guided Task Copilot — Visual Task Cards

**Where it lives**: a collapsible rail on the right edge of every portal page (distinct from the Workspace Assistant chat panel — this one is pure visual guidance, no typing required).

**What it shows**: a live-updating stack of task cards, one per outstanding action across the broker's whole caseload, each rendered as a clickable card:

```
┌─ CASE #1248 — Priya Shah ────────────────────────────┐
│ ⚠️  Action needed: Rate 5 shortlisted plans  │
│  2 of 5 rated · updated 3 min ago              │
│  [ Go rate plans → ]   [ Why this matters ]    │
└─────────────────────────────────────┘
```

- Each card is generated from the case's current state machine position (Section 5 of the main plan) — e.g. AWAITING\_BROKER\_REVIEW → "Rate shortlisted plans"; PAUSED\_NEEDS\_HUMAN → "Resolve halt: {halt\_reason}"; DNR\_DRAFT → "Review & sign off Demands & Needs record"
- Cards are **deterministic**, generated from the case's `state` + `halt_reasons` + `unrated_plan_count` fields — never LLM-authored, so the task list can never hallucinate a step that doesn't exist
- Primary button is a direct deep link (`/cases/:id/ranking`, `/cases/:id/dnr`, etc.) — one click takes the broker straight to the exact screen and scroll position needed
- Cards sort by priority score (see 10.8) — overdue and halted cases float to the top, shown with a red left-border accent
- Swipe-to-dismiss (or a ✓ button) temporarily snoozes a card for 1 hour — it reappears automatically; cards can never be permanently dismissed while the underlying task is incomplete

### 10.3 "Why This Matters" / Explain-My-Role Feature

Clicking **Why this matters** on any task card (or the (i) icon beside a case) opens a slide-over panel that explains, in plain language generated by the LLM from deterministic case facts:

- **What is the broker's job here**: "Your role in this case is to review the 5 AI-ranked plans, rate each one with your own professional judgment, and give a written reason — FCA ICOBS 5.3.4R requires this personalised explanation before the consumer can see any recommendation."
- **Why it's structured this way**: ties the required action back to the specific regulation or business rule (reuses the citation mechanism from Section 7.3)
- **How to do it well**: 2–3 concrete tips, e.g. "Plans with a stability score below 60% have a close runner-up — read both explanations before rating" or "If a plan is missing documents, that's flagged as a blocker; factor it into your YES/NO/REFER decision"
- **Estimated time**: a rough time estimate ("\~4 minutes") computed from the historical median time brokers take on this task type (same data source as Section 11 analytics)

This panel is generated via a dedicated LLM call (`/assistant/explain-task`) that receives ONLY the deterministic case facts (state, criterion scores, blockers) — never raw medical data — so it is subject to the same medical firewall as the main assistant (Section 9).

### 10.4 Real-Time Notifications — New Case & Pending Case Alerts

**Trigger events** (published via the existing SSE bus used for agent activity, Section 9 of the main plan):

| Event | Fires when | Notification shown |
| --- | --- | --- |
| `case.created` | A new case lands in the broker's queue | "🆕 New case: {consumer\_name} — {coverage\_type}" |
| `case.halted` | A case the broker owns hits a halt reason | "⏸ Case #{ref} paused: {halt\_reason}" |
| `case.sla_warning` | A case crosses 80% of its SLA window with no broker action | "⏰ Case #{ref} needs action — 2 days left" |
| `case.pending_today` | Daily 8am digest trigger (see 10.6) | "📄 {n} cases pending today" |
| `rating.unblocked` | All quotes received, ranking ready for review | "✅ Case #{ref} ready to rate" |

**Notification bell (top nav, every page)**:

- Badge shows unread count; red dot pulses once on new arrival (Framer Motion, disabled under reduced-motion)
- Click opens a dropdown inbox: list of notifications newest-first, each with icon, title, relative time ("3m ago"), and the case reference
- **Click a notification row → case link opens directly** (`navigate('/cases/' + caseId)`) and the notification is marked read
- "Mark all read" and a toggle for "Only show actionable" (hides informational-only events)
- Full inbox view at `/notifications` for history beyond the dropdown's last 20

**Toast pop-up (real-time, in addition to the bell)**:

- On `case.created` / `case.halted` / `rating.unblocked`, a toast slides in from the top-right over the dashboard (Sonner, 6-second auto-dismiss, hover to pause)
- Toast is itself clickable — clicking anywhere on it opens the case, same as the bell dropdown row
- Toasts are suppressed (queued into the bell only, no pop-up) when the broker is actively inside a different case's detail view, to avoid interrupting focused work
- Browser-level push notification (Web Push API, with broker opt-in) mirrors the toast when the portal tab is not focused or the browser is minimised

### 10.5 Login Priority Banner

On every login, immediately after authentication, a dismissible banner appears at the top of the dashboard:

```
📊 You have 3 cases needing action today — 1 overdue, 2 new.  [ Review priority queue → ]
```

- Computed server-side at login time from: overdue count (past SLA), new-since-last-login count, halted count
- "Review priority queue →" opens a pre-filtered queue view sorted by the same priority score as the task-card rail (10.8)
- Banner is dismissible for the session (reappears next login) — never permanently silenced, since priority facts change daily
- If zero priority items: banner shows a calmer "✅ You're all caught up" variant instead of hiding entirely, so the broker always gets a status signal on login

### 10.6 Architecture

```
[Case state change / webhook] → FastAPI event emitter → Postgres NOTIFY channel 'broker_events'
                                                        ↓
                                        FastAPI SSE endpoint /notifications/stream
                                         (one connection per logged-in broker, keyed by broker_id)
                                                        ↓
                        React NotificationProvider (EventSource, app-wide context)
                          ├─→ NotificationBell (badge count, dropdown)
                          ├─→ Toast layer (Sonner)
                          └─→ TaskCopilotRail (task cards, re-fetched on relevant events)

[Daily 08:00 cron, per broker timezone] → arq scheduled job 'daily_digest'
                                         → computes pending-today count → case.pending_today event
```

- Postgres `LISTEN/NOTIFY` on channel `broker_events` decouples event producers (case state machine, webhook ingestion, SLA cron) from the SSE fan-out layer — avoids a second message broker for v1; swappable for Redis pub/sub if broker count grows beyond \~500 concurrent connections
- SSE endpoint replays missed events on reconnect using the same cursor-based replay mechanism as the agent-activity SSE stream (main plan Section 9)
- Web Push (for browser-level notifications when tab is unfocused) uses the standard Push API + a service worker (`sw.js`) registered on first notification opt-in; VAPID keys stored server-side, subscription stored per-device in `push_subscriptions` table

### 10.7 Database Schema

```sql
CREATE TABLE notifications (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    broker_id   UUID NOT NULL REFERENCES brokers(id),
    case_id     UUID REFERENCES cases(id),
    event_type  TEXT NOT NULL,          -- 'case.created' | 'case.halted' | 'case.sla_warning' | ...
    title       TEXT NOT NULL,
    body        TEXT,
    read_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_notif_broker_unread ON notifications(broker_id) WHERE read_at IS NULL;

CREATE TABLE push_subscriptions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    broker_id   UUID NOT NULL REFERENCES brokers(id),
    endpoint    TEXT NOT NULL,
    keys_p256dh TEXT NOT NULL,
    keys_auth   TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE task_card_snoozes (
    broker_id   UUID NOT NULL REFERENCES brokers(id),
    case_id     UUID NOT NULL REFERENCES cases(id),
    task_key    TEXT NOT NULL,          -- deterministic key, e.g. 'rate_plans'
    snoozed_until TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (broker_id, case_id, task_key)
);
```

### 10.8 Priority Scoring (Deterministic — No LLM)

Each task card / queue row gets a priority score computed in code, never by the LLM:

```python
def priority_score(case) -> float:
    score = 0.0
    if case.state == 'PAUSED_NEEDS_HUMAN':
        score += 100
    days_since_action = (now() - case.last_broker_action_at).days
    sla_days_total = SLA_DAYS[case.coverage_type]
    sla_fraction_used = days_since_action / sla_days_total
    score += sla_fraction_used * 50
    if sla_fraction_used >= 1.0:
        score += 200  # overdue — always floats to top
    if case.state == 'AWAITING_BROKER_REVIEW':
        score += 30 * (1 - case.unrated_plan_fraction)  # more unrated plans = higher urgency
    return score
```

This function is unit-tested (`test_priority_deterministic`) to guarantee the same case inputs always yield the same score — brokers must be able to trust the ordering is explainable, auditable and reproducible, which an LLM-generated ranking could not guarantee.

### 10.9 Backend Endpoints

```
GET    /notifications/stream       → SSE connection, broker-scoped
GET    /notifications              → paginated inbox (read + unread)
POST   /notifications/{id}/read    → mark single notification read
POST   /notifications/read-all     → mark all read
POST   /notifications/push/subscribe → register a Web Push subscription
GET    /tasks/rail                 → current broker's task cards, priority-sorted
POST   /tasks/{case_id}/{task_key}/snooze → snooze a task card for 1 hour
POST   /assistant/explain-task     → LLM call for the "Why this matters" panel (Section 10.3)
GET    /dashboard/priority-summary → login banner counts (overdue, new, halted)
```

### 10.10 Researched Advancements for the Copilot & Notifications

Built on current patterns in AI-copilot UX and real-time notification architecture (generative/agentic UI, multi-channel alerting, proactive nudge design):

- **Generative UI task cards**: rather than fixed card templates, let the backend emit a small typed JSON schema per task (`{type: 'rate_plans', props: {...}}`) and render it through a component registry — new task types ship as new React components without touching the notification pipeline (the "copilot-as-UI" pattern, not copilot-as-chat)
- **Smart batching / digest mode**: if more than 3 notifications fire within a 2-minute window (e.g. a bulk webhook import), collapse them into a single "📥 5 new cases arrived" summary toast instead of 5 separate pop-ups, with the bell dropdown still listing each individually
- **Predictive SLA-breach nudges**: instead of only alerting at 80% of SLA, use the historical per-coverage-type median handling time (Section 11 data) to predict which cases are trending toward breach *today*, and surface those a day earlier than a fixed threshold would
- **Multi-channel escalation**: in-app toast → bell → (if still unread after N hours and case is overdue) email digest → (if the firm opts in) Slack/Teams webhook notification — configurable per broker in settings
- **Contextual snooze reasons**: when a broker snoozes a task, optionally capture a one-tap reason ("waiting on consumer", "waiting on insurer docs") — feeds directly into the blockers analytics in Section 11 without extra data entry
- **Role-aware escalation for senior brokers**: if a junior broker's case breaches SLA twice, auto-notify their senior\_broker (RBAC role from main plan Section 11) with a one-click "take over" action
- **Voice-announced priority banner**: on login, optionally read the priority banner aloud using the same text-to-speech hook as the Workspace Assistant (Section 7.4) — useful for accessibility and for brokers checking in via a hands-free device

---

## 11. Broker Insights & Analytics Dashboard

### 11.1 Purpose

A dedicated `/insights` page (extends the existing Insights dashboard from the main plan's Phase P8) giving brokers and senior brokers a data-driven view of their whole caseload: how fast cases move, where they get stuck, how satisfied consumers are, and which insurers and plan features actually win business. This turns the portal from a case-processing tool into a continuous feedback loop for the broker's own practice.

### 11.2 Metric Catalogue

**A. Case volume & aging**

- New cases per day / week / month / year (line chart, selectable granularity)
- Cases closed vs still open, stacked by month
- Case aging buckets: 0–2 days, 3–5 days, 6–10 days, 10+ days (bar chart) — shows where the current open caseload sits relative to SLA
- Average and median time-to-close, overall and broken down by coverage type and by case state (funnel view: time spent in each state of the 17-state machine)
- Oldest open cases table — sortable, clickable through to the case

**B. Satisfaction**

- Post-case consumer satisfaction score (CSAT, 1–5, collected via the magic-link post-publish survey) — trend line over time
- Satisfaction broken down by broker, by coverage type, by insurer selected
- Correlation view: satisfaction vs time-to-close, satisfaction vs number of plans shown

**C. Insurer / provider performance**

- Which insurers are most frequently in the broker's top-3 ranked plans (bar chart, "win rate")
- Which insurers are most frequently **selected** by the broker after rating (actual choice, not just ranked — shows where AI ranking and broker judgment agree or diverge)
- Average underwriting turnaround time per insurer (from `turnaroundDays` field, actuals vs quoted)
- Upheld complaint rate per insurer (from `insurerStats.upheldRate`) trended over time

**D. Plan & consumer choice patterns**

- Most commonly selected coverage levels (cancer/mental/outpatient tiers) — shows what consumers actually value
- Most common "must-have" filters requested (mustHave flags) — informs which criteria to surface more prominently in future UI
- Budget distribution of closed cases vs budget of cases still open (are higher-budget cases slower to close?)
- Preferred underwriting type distribution (moratorium vs full medical vs FMU)

**E. Broker productivity (compliance-safe — never used punitively without senior\_broker context)**

- Cases handled per broker per period
- Average rating time per plan (from `broker_ratings.created_at` deltas) — feeds the "estimated time" shown in Section 10.3
- Percentage of AI-draft reasons edited vs accepted as-is (`is_edited` field) — a proxy for how closely the broker reviews AI suggestions

### 11.3 Data Model

Metrics are computed from existing tables (`cases`, `broker_ratings`, `plans`, `audit_events`) plus two new aggregate/event tables:

```sql
CREATE TABLE case_satisfaction (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id     UUID NOT NULL REFERENCES cases(id),
    score       SMALLINT NOT NULL CHECK (score BETWEEN 1 AND 5),
    comment     TEXT,
    submitted_at TIMESTAMPTZ DEFAULT now()
);

-- Materialised view, refreshed every 15 min by an arq job, for fast dashboard reads
CREATE MATERIALIZED VIEW mv_case_daily_stats AS
SELECT
    date_trunc('day', created_at) AS day,
    coverage_type,
    broker_id,
    count(*) AS new_cases,
    count(*) FILTER (WHERE state IN ('PUBLISHED','CLOSED')) AS closed_cases,
    avg(EXTRACT(EPOCH FROM (closed_at - created_at)) / 86400) AS avg_days_to_close
FROM cases GROUP BY 1, 2, 3;
CREATE UNIQUE INDEX ON mv_case_daily_stats(day, coverage_type, broker_id);
```

### 11.4 Backend Aggregation Endpoints

```
GET /insights/volume?granularity=day|week|month|year&from=&to=&broker_id=
GET /insights/aging                     → bucketed open-case age distribution
GET /insights/time-to-close?by=state|coverage_type
GET /insights/satisfaction?by=broker|insurer|coverage_type
GET /insights/insurer-performance        → win rate, selection rate, turnaround, upheld rate per insurer
GET /insights/plan-patterns              → coverage tier distribution, must-have flags, underwriting type split
GET /insights/broker-productivity        → senior_broker / admin only (RBAC-gated)
```

All endpoints accept `from`/`to` date range params and return pre-aggregated rows from the materialised view (never raw per-case scans) to keep dashboard load under 300ms even with years of case history.

### 11.5 Frontend — Dashboard Layout

- Top row: 4 KPI tiles — Open cases, Avg days to close, CSAT (last 30d), Overdue cases — each with a small sparkline and a vs-last-period delta badge
- Volume chart: stacked area (new vs closed) with a granularity toggle (day/week/month/year)
- Aging bar chart with click-through: clicking a bucket filters the queue page to that age range
- Insurer performance table: sortable columns (win rate, selection rate, turnaround, upheld rate), small inline bar per cell
- Satisfaction trend line with an annotated band showing the UK insurance-sector benchmark (configurable)
- Filters bar: date range, coverage type, broker (senior\_broker/admin only), insurer — all filters composable and reflected in the URL query string for shareable/bookmarkable views
- All charts built per the project's dataviz guidance (consistent categorical/sequential palette, light+dark mode, accessible tooltips)

### 11.6 Researched Advancements for Insights & Analytics

Built on current insurance-broker performance-analytics and BI-dashboard practice (cohort tracking, benchmark overlays, anomaly detection, exportable broker scorecards):

- **Cohort retention view**: track consumers who return for renewal — "of cases closed 12 months ago, what % renewed through this broker" — a strong proxy for real-world satisfaction beyond the point-in-time CSAT score
- **Anomaly detection on case aging**: flag when a case's time-in-state exceeds 2 standard deviations from the historical median for that state and coverage type, surfaced as a proactive insight card ("This case is taking 3x longer than similar cases to leave DNR\_DRAFT") — feeds back into the Task Copilot (Section 10) as a priority-boosted card
- **Team / peer benchmarking**: for senior\_broker and admin roles, show a broker's metrics against the anonymised team median (never named peer-to-peer comparison, to avoid unhealthy competitive pressure) — "Your avg time-to-close is 4.2 days vs team median 5.1 days"
- **Exportable broker scorecard (PDF/CSV)**: one-click export of a broker's own period performance for appraisals or CPD records, reusing the project's existing PDF export skill
- **Choice-share funnel**: visualise the full funnel from "plans shown" → "plans rated highly" → "plans selected" → "consumer accepted" per insurer, to show exactly where an insurer's plans fall out of contention
- **Natural-language insight summaries**: a "Summarise my month" button (reusing the Workspace Assistant's streaming chat, Section 5) that turns the current filtered dashboard view into a 3-sentence plain-English summary — same medical-firewall and audit rules apply, since it is powered by the same assistant pipeline
- **Satisfaction driver analysis**: lightweight regression (scikit-learn, computed nightly, not an LLM) identifying which factors (time-to-close, number of plans shown, insurer chosen) correlate most strongly with CSAT, shown as a ranked "what moves satisfaction" list — clearly labelled as correlation, not causation

---

## 12. Phase WA2 — Paste-Ready Master Prompt (Task Copilot + Notifications + Insights)

Copy everything in the fenced block below into your coding assistant to implement Sections 10 and 11 in full.

```
ROLE: You are implementing Phase WA2 of the Helm broker portal: (A) a proactive,
visual Task Copilot with real-time notifications, and (B) a Broker Insights &
Analytics dashboard. Read Sections 10 and 11 of the project plan doc in full
before writing any code — they contain the exact schema, endpoints, scoring
formula, and UI behaviour you must implement.

HARD CONSTRAINTS (do not violate):
- Website code is React 18 + Vite + JSX ONLY. No TypeScript, no .tsx files.
- Backend is Python 3.12 + FastAPI, async throughout (asyncpg / SQLAlchemy 2 async).
- Task-card content and priority scores are DETERMINISTIC, computed in Python
  from case state/fields — the LLM is used ONLY for the "Why this matters"
  explanation text (Section 10.3) and the "Summarise my month" insight text
  (Section 11.6), never for deciding what task exists or its priority order.
- All LLM calls reuse the existing medical-data firewall (MF1–MF10) and PII
  redaction wrapper already built for the Workspace Assistant — do not
  construct a second, unguarded LLM path.
- Every notification, task-card view, and insights query is scoped to
  broker_id via RBAC — a broker must never see another broker's cases unless
  they hold the senior_broker or admin role querying explicitly in that
  capacity.
- All new DB objects (tables, materialised view) ship as Alembic migrations.

STEP 1 — Database layer
  Create Alembic migrations for: notifications, push_subscriptions,
  task_card_snoozes, case_satisfaction tables and the mv_case_daily_stats
  materialised view, exactly as specified in Sections 10.7 and 11.3. Add the
  arq scheduled job that refreshes the materialised view every 15 minutes and
  the daily 08:00-per-timezone digest job from Section 10.6.

STEP 2 — Event bus
  Implement the Postgres LISTEN/NOTIFY event emitter on channel
  'broker_events', fired from: the case state machine on every transition,
  the webhook ingestion handler on case.created, and the SLA-warning cron.
  Implement priority_score() exactly as specified in Section 10.8, with a
  unit test test_priority_deterministic that asserts identical inputs always
  produce identical scores (property-based test, run it 50 times with the
  same fixture).

STEP 3 — Notification backend
  Build all endpoints listed in Section 10.9: the SSE stream endpoint with
  cursor-based replay (reuse the existing agent-activity SSE replay
  mechanism, do not reinvent it), the paginated inbox, read/read-all,
  Web Push subscription registration (VAPID), and the task-rail and
  priority-summary endpoints. Rate-limit the SSE endpoint to one connection
  per broker (reject a second with 409 and a clear error).

STEP 4 — Task Copilot frontend (JSX)
  Build TaskCopilotRail.jsx as a collapsible right-edge rail present on every
  authenticated page (mount it in the root layout, not per-page). Each task
  card is rendered through a small component registry keyed by a 'type'
  field in the task JSON (generative-UI pattern from Section 10.10) so new
  task types can be added as new components without touching the rail
  itself. Implement swipe/click-to-snooze calling POST
  /tasks/{case_id}/{task_key}/snooze. Build the "Why this matters" slide-over
  panel that calls POST /assistant/explain-task and renders the response with
  the same citation-chip component used by the Workspace Assistant (Section
  7.3) so regulatory citations look consistent across both surfaces.

STEP 5 — Notifications frontend (JSX)
  Build a NotificationProvider (React context) wrapping the app, holding an
  EventSource connected to /notifications/stream, exposing unread count and
  the live list to any component. Build NotificationBell.jsx (badge + dropdown
  inbox, click-through to case) and the Sonner-based toast layer with the
  batching/digest behaviour from Section 10.10 (collapse >3 events in a
  2-minute window into one summary toast). Build the dismissible login
  priority banner reading from GET /dashboard/priority-summary, including the
  calm "You're all caught up" state when counts are zero. Wire up Web Push
  opt-in (service worker registration + subscription POST) behind a clear,
  dismissible in-app prompt — never request the browser permission silently
  on page load.

STEP 6 — Insights backend
  Implement every endpoint in Section 11.4, reading only from
  mv_case_daily_stats and existing tables — never raw per-case table scans on
  a hot path. Add the RBAC check so /insights/broker-productivity is
  senior_broker/admin only (403 for plain broker role, enforced server-side,
  never just hidden in the UI). Implement the satisfaction-driver regression
  job from Section 11.6 as a standalone nightly script (scikit-learn,
  plain linear/logistic regression — not an LLM), writing its ranked output
  to a small 'satisfaction_drivers' table the dashboard reads.

STEP 7 — Insights frontend (JSX)
  Build the /insights dashboard exactly as laid out in Section 11.5: 4 KPI
  tiles with sparklines, volume stacked-area chart with granularity toggle,
  clickable aging bar chart (click-through filters the queue), sortable
  insurer-performance table, satisfaction trend line with a configurable
  benchmark band, and a composable filters bar that reflects into the URL
  query string. Follow the project's dataviz guidance for all chart colours,
  light/dark mode, and accessible tooltips. Add the cohort retention view,
  anomaly-flagged insight cards (feeding into the Task Copilot's priority
  score as a boost, per Section 11.6), the exportable PDF/CSV scorecard, the
  choice-share funnel, and the "Summarise my month" button (reusing the
  Workspace Assistant streaming chat infrastructure from Section 5, with the
  current dashboard filter state passed as additional context).

STEP 8 — Tests & acceptance
  - Unit tests: priority_score determinism, medical-firewall scrub applied to
    both new LLM call sites, RBAC denial on broker-productivity endpoint for
    plain broker role.
  - Integration test: simulate a case.created webhook → assert SSE event
    received within 2s → assert notification row created → assert toast
    click navigates to the correct case route.
  - E2E test: login → priority banner shows correct counts → click → queue
    pre-filtered correctly → open a case → task card for that case's current
    state is present and its deep link lands on the correct screen.
  - Load test: materialised view refresh under 2s with 100,000 case rows;
    /insights/* endpoints respond under 300ms p95 against that dataset.

Deliver STEP 1–2 first as a reviewable unit (schema + event bus), then STEP
3–5 (notifications + copilot) as a second unit, then STEP 6–7 (insights) as a
third unit, each with its own passing test suite before moving on.
```
