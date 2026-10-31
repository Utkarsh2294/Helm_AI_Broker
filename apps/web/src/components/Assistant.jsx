import React, { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Bookmark,
  Check,
  Copy,
  Download,
  History,
  MessageSquare,
  Mic,
  Paperclip,
  Pin,
  Send,
  Volume2,
  X,
} from 'lucide-react';
import { api } from '../api';
import { useSessionStore } from '../session-store';

const workspaceChips = [
  'Summarise my workspace',
  'What needs attention today?',
  'Show blocked cases',
  'Pipeline overview',
];
const caseChips = [
  'What should I do next?',
  'What are the client’s preferences?',
  'Why this ranking?',
  'What did each agent do?',
];
const root = '/workspace/assistant';

function download(blob, name) {
  const url = URL.createObjectURL(blob),
    anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function Assistant({ caseId, onNavigate, onOpenCase, docked = false, onClose }) {
  const user = useSessionStore((state) => state.user);
  const [messages, setMessages] = useState([]),
    [question, setQuestion] = useState('');
  const [busy, setBusy] = useState(false),
    [uploading, setUploading] = useState(false),
    [error, setError] = useState('');
  const [attachments, setAttachments] = useState([]),
    [notice, setNotice] = useState('');
  const [historyOpen, setHistoryOpen] = useState(false),
    [history, setHistory] = useState([]),
    [search, setSearch] = useState('');
  const [evidence, setEvidence] = useState([]),
    [evidenceOpen, setEvidenceOpen] = useState(false);
  const [listening, setListening] = useState(false),
    [readAloud, setReadAloud] = useState(false);
  const [shareLink, setShareLink] = useState('');
  const [targetCase, setTargetCase] = useState(''),
    [targetCases, setTargetCases] = useState([]);
  const id = useId(),
    input = useRef(null),
    fileInput = useRef(null),
    end = useRef(null);
  const generation = useRef(0),
    controller = useRef(null),
    recognition = useRef(null),
    working = useRef(false);
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const speechAvailable = Boolean(window.speechSynthesis);
  const preferenceKey = `helm-assistant-read-aloud:${user?.id || 'local'}`;

  useEffect(() => {
    try {
      setReadAloud(localStorage.getItem(preferenceKey) === 'true');
    } catch {
      /* Storage may be disabled. */
    }
  }, [preferenceKey]);
  useEffect(() => {
    if (docked) input.current?.focus();
  }, [docked]);
  useEffect(() => {
    generation.current += 1;
    controller.current?.abort();
    working.current = false;
    setBusy(false);
    setUploading(false);
    setMessages([]);
    setAttachments([]);
    setQuestion('');
    setError('');
    setNotice('');
    setShareLink('');
    setHistory([]);
    setEvidence([]);
    setHistoryOpen(false);
    setEvidenceOpen(false);
    if (caseId)
      api(`${root}/evidence?case_id=${encodeURIComponent(caseId)}`)
        .then(setEvidence)
        .catch(() => {});
    return () => {
      generation.current += 1;
      controller.current?.abort();
      recognition.current?.abort();
      window.speechSynthesis?.cancel();
    };
  }, [caseId]);
  useEffect(() => {
    if (!historyOpen) return;
    let active = true;
    const timer = setTimeout(
      () =>
        api(
          `${root}/history?${caseId ? `case_id=${encodeURIComponent(caseId)}&` : ''}q=${encodeURIComponent(search)}`,
        )
          .then((rows) => {
            if (active) setHistory(rows);
          })
          .catch((cause) => {
            if (active) setError(cause.message);
          }),
      180,
    );
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [historyOpen, search, caseId]);
  useEffect(() => {
    if (caseId || !attachments.length) return;
    let active = true;
    api('/cases?limit=50')
      .then((result) => {
        if (active) setTargetCases(result.items);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [caseId, attachments.length]);

  function speak(text) {
    if (!speechAvailable) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'en-GB';
    const voice = window.speechSynthesis.getVoices().find((item) => item.lang === 'en-GB');
    if (voice) utterance.voice = voice;
    window.speechSynthesis.speak(utterance);
  }
  async function ask(value) {
    if (working.current || uploading || !value.trim()) return;
    const epoch = generation.current;
    working.current = true;
    setBusy(true);
    setError('');
    setNotice('');
    setQuestion('');
    setMessages((previous) =>
      [
        ...previous,
        { role: 'broker', text: value },
        { role: 'assistant', text: '', pending: true },
      ].slice(-40),
    );
    const abort = new AbortController();
    controller.current = abort;
    let result = { role: 'assistant', text: '', pending: true },
      buffer = '';
    try {
      const stream = await api(`${root}/stream`, {
        method: 'POST',
        body: {
          question: value,
          case_id: caseId || null,
          file_ids: attachments.map((file) => file.id),
        },
        responseType: 'stream',
        signal: abort.signal,
      });
      const reader = stream.getReader(),
        decoder = new TextDecoder();
      let complete = false;
      while (true) {
        const { value: chunk, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(chunk, { stream: true }).replaceAll('\r\n', '\n');
        let boundary;
        while ((boundary = buffer.indexOf('\n\n')) !== -1) {
          const block = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          const type = block
            .split('\n')
            .find((line) => line.startsWith('event: '))
            ?.slice(7);
          const data = JSON.parse(
            block
              .split('\n')
              .filter((line) => line.startsWith('data: '))
              .map((line) => line.slice(6))
              .join('\n') || '{}',
          );
          if (type === 'metadata') result = { ...result, ...data };
          if (type === 'delta') result.text += data.text;
          if (type === 'done') {
            result.pending = false;
            complete = true;
          }
          if (epoch === generation.current)
            setMessages((previous) => [...previous.slice(0, -1), { ...result }]);
        }
      }
      if (!complete)
        throw new Error(
          'The response was interrupted. Retry the question or check History for the saved answer.',
        );
      if (epoch === generation.current && readAloud) speak(result.text);
    } catch (cause) {
      if (epoch === generation.current && cause.name !== 'AbortError') {
        setError(cause.message);
        setQuestion(value);
        setMessages((previous) => previous.filter((message) => !message.pending));
      }
    } finally {
      if (epoch === generation.current) {
        working.current = false;
        setBusy(false);
        end.current?.scrollIntoView({ block: 'nearest', behavior: 'instant' });
      }
    }
  }
  async function act(action) {
    setError('');
    try {
      await action();
    } catch (cause) {
      setError(cause.message);
    }
  }
  async function upload(files) {
    if (uploading || busy) return;
    const epoch = generation.current;
    setUploading(true);
    setError('');
    try {
      if (attachments.length + files.length > 5)
        throw new Error('Attach at most five files at a time.');
      for (const file of files) {
        if (file.size > 20 * 1024 * 1024) throw new Error(`${file.name} exceeds 20 MB.`);
        const content = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result).split(',')[1]);
          reader.onerror = () => reject(new Error('The file could not be read.'));
          reader.readAsDataURL(file);
        });
        const parsed = await api(`${root}/files`, {
          method: 'POST',
          body: { name: file.name, content_base64: content, case_id: caseId || null },
        });
        if (epoch === generation.current) {
          setAttachments((previous) => [...previous, parsed]);
          setNotice(`Received and parsed ${parsed.name}. ${parsed.notice}`);
        }
      }
    } catch (cause) {
      if (epoch === generation.current) setError(cause.message);
    } finally {
      if (epoch === generation.current) setUploading(false);
      if (fileInput.current) fileInput.current.value = '';
    }
  }
  function dictate() {
    if (listening) {
      recognition.current?.stop();
      return;
    }
    if (!SpeechRecognition) return;
    const engine = new SpeechRecognition();
    recognition.current = engine;
    engine.lang = 'en-GB';
    engine.interimResults = false;
    engine.maxAlternatives = 1;
    engine.onresult = (event) =>
      setQuestion((value) => `${value} ${event.results[0][0].transcript}`.trim().slice(0, 1500));
    engine.onerror = () =>
      setError('Voice input was unavailable or permission was denied. Type your question instead.');
    engine.onend = () => setListening(false);
    try {
      engine.start();
      setListening(true);
    } catch {
      setError('Voice input could not start. Type your question instead.');
    }
  }
  const answers = messages.filter((message) => message.id && !message.pending);
  const latest = answers.at(-1);
  return (
    <section
      className={`case-assistant ${docked ? 'assistant-docked' : ''}`}
      aria-labelledby={`${id}-title`}
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        upload([...event.dataTransfer.files]);
      }}
    >
      <div className="section-header">
        <h3 id={`${id}-title`}>
          <MessageSquare size={19} />
          {caseId ? 'Your case assistant' : 'Your workspace assistant'}
        </h3>
        {docked ? (
          <button className="icon-button" aria-label="Close assistant panel" onClick={onClose}>
            <X size={18} />
          </button>
        ) : (
          <button
            className="button small"
            onClick={() => window.dispatchEvent(new CustomEvent('helm:assistant-open'))}
          >
            <Pin size={15} />
            Pin panel
          </button>
        )}
      </div>
      <p className="muted">
        Answers use local saved records. Policy selection and final approval stay with you.{' '}
        {caseId ? 'Scoped to this case.' : 'Scoped to your accessible workspace.'}
      </p>
      <div className="assistant-toolbar">
        <button
          className="button small"
          aria-expanded={historyOpen}
          onClick={() => setHistoryOpen(!historyOpen)}
        >
          <History size={15} />
          History
        </button>
        {caseId && (
          <button
            className="button small"
            aria-expanded={evidenceOpen}
            onClick={() => {
              setEvidenceOpen(!evidenceOpen);
              act(async () =>
                setEvidence(await api(`${root}/evidence?case_id=${encodeURIComponent(caseId)}`)),
              );
            }}
          >
            <Bookmark size={15} />
            Evidence ({evidence.length})
          </button>
        )}
        <button
          className="button small"
          disabled={!speechAvailable}
          aria-pressed={readAloud}
          onClick={() => {
            const enabled = !readAloud;
            setReadAloud(enabled);
            try {
              localStorage.setItem(preferenceKey, String(enabled));
            } catch {
              /* Optional preference. */
            }
            if (!enabled) window.speechSynthesis?.cancel();
          }}
        >
          <Volume2 size={15} />
          Read aloud {readAloud ? 'on' : 'off'}
        </button>
        {['pdf', 'docx'].map((format) => (
          <button
            key={format}
            className="button small"
            disabled={!answers.length || busy}
            onClick={() =>
              act(async () =>
                download(
                  await api(`${root}/export`, {
                    method: 'POST',
                    body: { log_ids: answers.map((message) => message.id), format },
                    responseType: 'blob',
                  }),
                  `helm-assistant.${format}`,
                ),
              )
            }
          >
            <Download size={15} />
            {format.toUpperCase()}
          </button>
        ))}
      </div>
      {historyOpen && (
        <div className="assistant-history">
          <label htmlFor={`${id}-history`}>
            Search your last 20 queries {caseId ? 'for this case' : 'in the workspace'}
          </label>
          <input
            id={`${id}-history`}
            value={search}
            maxLength={1500}
            onChange={(event) => setSearch(event.target.value)}
          />
          {history.length ? (
            history.map((entry) => (
              <div key={entry.id}>
                <button className="text-button" disabled={busy} onClick={() => ask(entry.question)}>
                  {entry.question}
                </button>
                <small>
                  {new Date(entry.timestamp).toLocaleString('en-GB')} · {entry.confidence}
                </small>
                <details>
                  <summary>Saved answer</summary>
                  <p>{entry.answer}</p>
                </details>
              </div>
            ))
          ) : (
            <p className="muted">No matching saved queries.</p>
          )}
        </div>
      )}
      {evidenceOpen && (
        <div className="assistant-evidence">
          <h4>Saved case evidence</h4>
          {evidence.length ? (
            evidence.map((entry) => (
              <details key={entry.id}>
                <summary>{entry.question}</summary>
                <p>{entry.answer}</p>
                <small>
                  {entry.timestamp} · {entry.model_version}
                </small>
              </details>
            ))
          ) : (
            <p>No assistant answers saved yet. Use Save to evidence on an answer.</p>
          )}
        </div>
      )}
      <div className="assistant-suggestions">
        {(caseId ? caseChips : workspaceChips).map((text) => (
          <button
            key={text}
            className="button small"
            disabled={busy || uploading}
            onClick={() => ask(text)}
          >
            {text}
          </button>
        ))}
      </div>
      <div
        className="assistant-messages"
        role="log"
        aria-label="Assistant conversation"
        aria-live="polite"
        aria-busy={busy}
      >
        {messages.map((message, index) => (
          <article className={`assistant-message ${message.role}`} key={message.id || index}>
            <strong>
              {message.role === 'broker'
                ? 'You'
                : caseId
                  ? 'Helm Case Assistant'
                  : 'Helm Workspace Assistant'}
            </strong>
            <p>
              {(message.text || 'Reading the saved records…')
                .split(/(\[\d+\])/)
                .map((part, number) =>
                  /^\[\d+\]$/.test(part) && message.sources?.[Number(part.slice(1, -1)) - 1] ? (
                    <a
                      key={number}
                      href={`#${id}-source-${index}-${part.slice(1, -1)}`}
                      onClick={() => {
                        const element = document.getElementById(
                          `${id}-source-${index}-${part.slice(1, -1)}`,
                        );
                        if (element) element.closest('details').open = true;
                      }}
                    >
                      {part}
                    </a>
                  ) : (
                    part
                  ),
                )}
            </p>
            {message.table && (
              <div
                className="assistant-table"
                tabIndex={0}
                role="region"
                aria-label="Scrollable saved policy comparison"
              >
                <table>
                  <caption>Saved policy comparison</caption>
                  <thead>
                    <tr>
                      {message.table.columns.map((column) => (
                        <th key={column}>{column}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {message.table.rows.map((row, i) => (
                      <tr key={i}>
                        {row.map((cell, j) => (
                          <td key={j}>{cell}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {message.id && !message.pending && (
              <>
                <small className="assistant-stamp">
                  {message.confidence} · Saved-record confidence, not suitability assurance
                  <br />
                  {new Date(message.timestamp).toLocaleString('en-GB')} · Broker {message.broker_id}{' '}
                  · {message.model_version}
                </small>
                {message.compliance_context?.length > 0 && (
                  <p className="notice warning">
                    Review context: {message.compliance_context.join('; ')}. Check your approved
                    rule text; this is not a regulatory finding.
                  </p>
                )}
                <details className="assistant-citations">
                  <summary>Sources ({message.sources?.length || 0})</summary>
                  {message.sources?.map((source, i) => (
                    <div id={`${id}-source-${index}-${i + 1}`} key={i}>
                      {source.case_id || source.view ? (
                        <button
                          className="text-button"
                          onClick={() =>
                            source.case_id
                              ? onOpenCase?.(source.case_id)
                              : onNavigate?.(source.view)
                          }
                        >
                          [{i + 1}] {source.label}
                        </button>
                      ) : (
                        <p>
                          [{i + 1}] {source.label}
                        </p>
                      )}
                      <code>{source.record || source.sha256}</code>
                    </div>
                  ))}
                </details>
                <div className="assistant-toolbar">
                  <button
                    className="button small"
                    onClick={() =>
                      act(async () => {
                        await navigator.clipboard.writeText(message.text);
                        setNotice('Answer copied.');
                      })
                    }
                  >
                    <Copy size={14} />
                    Copy
                  </button>
                  {caseId && (
                    <button
                      className="button small"
                      disabled={message.saved}
                      onClick={() =>
                        act(async () => {
                          await api(`${root}/${message.id}/evidence`, { method: 'POST' });
                          setMessages((previous) =>
                            previous.map((entry) =>
                              entry.id === message.id ? { ...entry, saved: true } : entry,
                            ),
                          );
                          setEvidence(
                            await api(`${root}/evidence?case_id=${encodeURIComponent(caseId)}`),
                          );
                          setNotice('Answer and source snapshot saved to case evidence.');
                        })
                      }
                    >
                      {message.saved ? <Check size={14} /> : <Bookmark size={14} />}
                      {message.saved ? 'Saved to evidence' : 'Save to evidence'}
                    </button>
                  )}
                  {speechAvailable && (
                    <button className="button small" onClick={() => speak(message.text)}>
                      <Volume2 size={14} />
                      Listen
                    </button>
                  )}
                  {caseId && (
                    <button
                      className="button small"
                      onClick={() =>
                        act(async () => {
                          const link = await api(`${root}/${message.id}/share`, { method: 'POST' });
                          setShareLink(new URL(link.path, window.location.origin).href);
                          setNotice(
                            `Review link expires ${new Date(link.expires_at).toLocaleString('en-GB')}. A compliance officer must sign in.`,
                          );
                        })
                      }
                    >
                      Share for compliance
                    </button>
                  )}
                </div>
              </>
            )}
          </article>
        ))}
        <div ref={end} />
      </div>
      {latest && (
        <div className="assistant-suggestions" aria-label="Suggested follow-up questions">
          {latest.suggestions?.map((text) => (
            <button
              key={text}
              className="button small"
              disabled={busy || uploading}
              onClick={() => ask(text)}
            >
              {text}
            </button>
          ))}
        </div>
      )}
      {notice && (
        <p role="status" className="assistant-notice">
          {notice}
        </p>
      )}
      {shareLink && (
        <div className="assistant-share">
          <label htmlFor={`${id}-share`}>Read-only compliance review link</label>
          <input
            id={`${id}-share`}
            readOnly
            value={shareLink}
            onFocus={(event) => event.target.select()}
          />
          <button
            className="button small"
            onClick={() =>
              act(async () => {
                await navigator.clipboard.writeText(shareLink);
                setNotice('Review link copied.');
              })
            }
          >
            Copy link
          </button>
        </div>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <form
        className="assistant-input"
        onSubmit={(event) => {
          event.preventDefault();
          ask(question);
        }}
      >
        <label htmlFor={`${id}-question`}>
          Ask {caseId ? 'about this case' : 'about your workspace'}
        </label>
        <div>
          <input
            ref={input}
            id={`${id}-question`}
            value={question}
            maxLength={1500}
            required
            onChange={(event) => setQuestion(event.target.value)}
            placeholder={
              caseId
                ? 'For example: Why is Northgate ranked first?'
                : 'For example: What needs attention today?'
            }
          />
          <button
            className="button primary"
            disabled={busy || uploading || !question.trim()}
            aria-label="Send question"
          >
            <Send size={18} />
          </button>
        </div>
        <div className="assistant-toolbar">
          <input
            ref={fileInput}
            type="file"
            multiple
            accept=".pdf,.docx,.xlsx,.csv,.png,.jpg,.jpeg,.webp,.txt"
            hidden
            onChange={(event) => upload([...event.target.files])}
          />
          <button
            type="button"
            className="button small"
            disabled={uploading || busy}
            onClick={() => fileInput.current?.click()}
          >
            <Paperclip size={16} />
            {uploading ? 'Parsing locally…' : 'Attach files'}
          </button>
          <button
            type="button"
            className={`button small ${listening ? 'assistant-recording' : ''}`}
            disabled={!SpeechRecognition || busy}
            aria-pressed={listening}
            onClick={dictate}
          >
            <Mic size={16} />
            {listening ? 'Stop recording' : 'Voice input'}
          </button>
        </div>
        <small className="muted">
          Drop files here · Up to 5 files, 20 MB each.{' '}
          {SpeechRecognition
            ? 'Voice uses your browser’s speech service; review the transcript before sending.'
            : 'Voice recognition is not supported in this browser. Type your question instead.'}{' '}
          Case document analysis requires verified medical access.
        </small>
        {attachments.map((file) => (
          <div className="assistant-attachment" key={file.id}>
            <span>
              {file.name}
              {file.truncated ? ' · extract limited to 60,000 characters' : ''}
            </span>
            <button
              className="icon-button"
              type="button"
              aria-label={`Remove ${file.name}`}
              onClick={() =>
                setAttachments((previous) => previous.filter((entry) => entry.id !== file.id))
              }
            >
              <X size={15} />
            </button>
            <button
              type="button"
              className="button small"
              disabled={file.attached || (!caseId && !targetCase)}
              onClick={() =>
                act(async () => {
                  await api(`${root}/files/${file.id}/attach`, {
                    method: 'POST',
                    body: { case_id: caseId || targetCase },
                  });
                  setAttachments((previous) =>
                    previous.map((item) =>
                      item.id === file.id ? { ...item, attached: true } : item,
                    ),
                  );
                  setNotice(
                    'Extract attached to the digital client file. No preferences were changed.',
                  );
                })
              }
            >
              {file.attached ? 'Extract attached' : 'Attach extract to case'}
            </button>
          </div>
        ))}
        {!caseId && attachments.length > 0 && (
          <div>
            <label htmlFor={`${id}-target`}>Case for this document extract</label>
            <select
              id={`${id}-target`}
              value={targetCase}
              onChange={(event) => setTargetCase(event.target.value)}
            >
              <option value="">Choose an accessible case</option>
              {targetCases.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
            <small>
              Verified medical access to the chosen case is required. The original file is not
              retained.
            </small>
          </div>
        )}
      </form>
    </section>
  );
}

export function AssistantDock() {
  const [open, setOpen] = useState(false),
    [host, setHost] = useState(null);
  const location = useLocation(),
    navigate = useNavigate(),
    origin = useRef(null);
  const caseId = location.pathname.startsWith('/case/')
    ? decodeURIComponent(location.pathname.slice(6))
    : null;
  useEffect(() => {
    function show() {
      origin.current = document.activeElement;
      setOpen(true);
    }
    function shortcut(event) {
      if ((event.ctrlKey || event.metaKey) && !event.shiftKey && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        show();
      }
    }
    window.addEventListener('helm:assistant-open', show);
    window.addEventListener('keydown', shortcut);
    return () => {
      window.removeEventListener('helm:assistant-open', show);
      window.removeEventListener('keydown', shortcut);
    };
  }, []);
  useEffect(() => {
    if (!open) return;
    const update = () =>
      setHost(document.querySelector('dialog[open] .panel-body') || document.body);
    update();
    const observer = new MutationObserver(update);
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['open'],
    });
    return () => observer.disconnect();
  }, [open, caseId]);
  function close() {
    setOpen(false);
    origin.current?.focus();
  }
  useEffect(() => {
    if (!open) return;
    function escape(event) {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        setOpen(false);
        origin.current?.focus();
      }
    }
    document.addEventListener('keydown', escape, true);
    return () => document.removeEventListener('keydown', escape, true);
  }, [open]);
  if (!open || !host) return null;
  return createPortal(
    <aside className="assistant-dock" aria-label="Pinned assistant panel">
      <Assistant
        key={caseId || 'workspace'}
        caseId={caseId}
        docked
        onClose={close}
        onOpenCase={(id) => {
          setOpen(false);
          navigate(`/case/${encodeURIComponent(id)}`);
        }}
        onNavigate={(view) => {
          setOpen(false);
          navigate(`/case/${encodeURIComponent(caseId)}?view=${view}`);
        }}
      />
    </aside>,
    host,
  );
}

export function AssistantReview() {
  const location = useLocation();
  const [data, setData] = useState(null),
    [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    api(`${root}/shared/${encodeURIComponent(location.pathname.split('/').at(-1))}`)
      .then((value) => {
        if (active) setData(value);
      })
      .catch((cause) => {
        if (active) setError(cause.message);
      });
    return () => {
      active = false;
    };
  }, [location.pathname]);
  return (
    <section className="case-assistant">
      <h1>Read-only assistant review</h1>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {data && (
        <>
          <h2>{data.question}</h2>
          <p className="assistant-review-answer">{data.answer}</p>
          <p>
            {data.confidence} · {data.timestamp} · Broker {data.broker_id} · {data.model_version}
          </p>
          <ol>
            {data.sources.map((source, index) => (
              <li key={index}>
                {source.label}
                <br />
                <code>{source.record || source.sha256}</code>
              </li>
            ))}
          </ol>
          <p>
            Expires {new Date(data.expires_at).toLocaleString('en-GB')}. This page cannot change the
            case or approve advice.
          </p>
        </>
      )}
    </section>
  );
}
