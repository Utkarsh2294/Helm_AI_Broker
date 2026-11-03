import React, { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useLocation, useNavigate } from 'react-router-dom';
import { motion, useMotionValue, useReducedMotion } from 'framer-motion';
import { useDrag } from '@use-gesture/react';
import { toast } from 'sonner';
import { useDictation, useReadAloud } from '../hooks/useAssistantAudio';
import usePanelHost from '../hooks/usePanelHost';
import AssistantCitations from './AssistantCitations';
import AssistantCasePicker from './AssistantCasePicker';
import keepPanelFocus from '../hooks/keepPanelFocus';
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
  Pause,
  Play,
  Square,
  Trash2,
} from 'lucide-react';
import { api } from '../api';
import { caseIdFromPath } from '../case-route';
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
  const location = useLocation();
  const user = useSessionStore((state) => state.user);
  const [messages, setMessages] = useState([]),
    [question, setQuestion] = useState('');
  const [busy, setBusy] = useState(false),
    [uploading, setUploading] = useState(false),
    [error, setError] = useState('');
  const [attachments, setAttachments] = useState([]),
    [notice, setNotice] = useState('');
  const [historyOpen, setHistoryOpen] = useState(false),
    [search, setSearch] = useState('');
  const [evidence, setEvidence] = useState([]),
    [evidenceOpen, setEvidenceOpen] = useState(false);
  const [readAloud, setReadAloud] = useState(false);
  const [capabilities, setCapabilities] = useState(null),
    [context, setContext] = useState(null),
    [storageReady, setStorageReady] = useState(false),
    [savingMessage, setSavingMessage] = useState(null);
  const [shareLink, setShareLink] = useState('');
  const [targetCase, setTargetCase] = useState(''),
    [targetCases, setTargetCases] = useState([]);
  const id = useId(),
    input = useRef(null),
    fileInput = useRef(null),
    end = useRef(null);
  const generation = useRef(0),
    controller = useRef(null),
    working = useRef(false);
  const dictation = useDictation({
      caseId,
      onText: setQuestion,
      onNotice: setNotice,
      onError: setError,
    }),
    speaker = useReadAloud();
  const speechAvailable = speaker.available;
  const page = caseId
    ? 'case'
    : location.pathname === '/insights'
      ? 'insights'
      : ['/queue', '/priority-queue'].includes(location.pathname)
        ? 'queue'
        : 'workspace';
  const scope = caseId || 'workspace',
    historyKey = `helm_assistant_history_${user?.id}`;
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
    setStorageReady(false);
    setContext(null);
    setSavingMessage(null);
    setEvidence([]);
    setHistoryOpen(false);
    setEvidenceOpen(false);
    const epoch = generation.current;
    Promise.all([
      api('/assistant/capabilities'),
      api(`/assistant/context${caseId ? `?case_id=${encodeURIComponent(caseId)}` : ''}`),
    ])
      .then(([caps, current]) => {
        if (epoch !== generation.current) return;
        setCapabilities(caps);
        setContext(current);
        try {
          const saved = JSON.parse(localStorage.getItem(historyKey) || 'null');
          if (saved?.session === caps.history_session)
            setMessages(saved.messages.filter((entry) => entry.scope === scope).slice(-20));
          else localStorage.removeItem(historyKey);
        } catch {
          /* Browser storage is optional. */
        }
        setStorageReady(true);
      })
      .catch((cause) => {
        if (epoch === generation.current) setError(cause.message);
      });
    if (caseId)
      api(`${root}/evidence?case_id=${encodeURIComponent(caseId)}`)
        .then(setEvidence)
        .catch(() => {});
    return () => {
      generation.current += 1;
      controller.current?.abort();
      window.speechSynthesis?.cancel();
    };
  }, [caseId, user?.id]);
  useEffect(() => {
    if (!storageReady || !capabilities) return;
    try {
      const saved = JSON.parse(localStorage.getItem(historyKey) || 'null');
      const other =
        saved?.session === capabilities.history_session
          ? saved.messages.filter((entry) => entry.scope !== scope)
          : [];
      localStorage.setItem(
        historyKey,
        JSON.stringify({
          session: capabilities.history_session,
          messages: [
            ...other,
            ...messages.filter((entry) => !entry.pending).map((entry) => ({ ...entry, scope })),
          ].slice(-20),
        }),
      );
    } catch {
      /* Chat still works when storage is unavailable. */
    }
  }, [messages, storageReady, capabilities, historyKey, scope]);
  useEffect(() => {
    const clear = () => {
      try {
        localStorage.removeItem(historyKey);
      } catch {
        /* Optional storage. */
      }
      setMessages([]);
    };
    window.addEventListener('helm:assistant-clear-session', clear);
    window.addEventListener('helm:session-expired', clear);
    return () => {
      window.removeEventListener('helm:assistant-clear-session', clear);
      window.removeEventListener('helm:session-expired', clear);
    };
  }, [historyKey]);
  useEffect(() => {
    if (!context?.medical_access_expires) return;
    const timer = setTimeout(
      () => setContext((value) => ({ ...value, medical_access_expires: null })),
      Math.max(0, new Date(context.medical_access_expires).getTime() - Date.now()),
    );
    return () => clearTimeout(timer);
  }, [context?.medical_access_expires]);
  useEffect(() => {
    if (caseId || (!attachments.length && !savingMessage)) return;
    let active = true;
    api('/cases?limit=50')
      .then((result) => {
        if (active) setTargetCases(result.items);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [caseId, attachments.length, savingMessage]);

  async function ask(value) {
    if (!storageReady || working.current || uploading || !value.trim()) return;
    const epoch = generation.current;
    working.current = true;
    setBusy(true);
    setError('');
    setNotice('');
    speaker.stop();
    dictation.stop(true);
    setQuestion('');
    setMessages((previous) =>
      [
        ...previous,
        { role: 'broker', text: value },
        { role: 'assistant', text: '', pending: true },
      ].slice(-20),
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
          previous_question:
            messages
              .filter((message) => message.role === 'assistant')
              .at(-1)
              ?.resolved_question?.slice(0, 1500) ||
            messages
              .filter((message) => message.role === 'broker')
              .at(-1)
              ?.text?.slice(0, 1500) ||
            '',
          page,
          context_filters: Object.fromEntries(
            [...new URLSearchParams(location.search)].filter(([key]) =>
              ['from', 'to', 'coverage_type', 'broker_id', 'insurer_id'].includes(key),
            ),
          ),
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
      if (epoch === generation.current && readAloud) speaker.speak(result.text, result.id);
      if (epoch === generation.current && result.protected && caseId)
        api(`/assistant/context?case_id=${encodeURIComponent(caseId)}`)
          .then((current) => {
            if (epoch === generation.current) setContext(current);
          })
          .catch(() => {});
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
      let combinedCharacters = attachments.reduce(
        (total, file) => total + (file.characters || 0),
        0,
      );
      const attached = new Set(attachments.map((file) => file.id));
      if (attachments.length + files.length > 5)
        throw new Error('Attach at most five files at a time.');
      for (const file of files) {
        if (file.size > 25 * 1024 * 1024) throw new Error(`${file.name} exceeds 25 MB.`);
        const form = new FormData();
        form.append('files', file);
        if (caseId) form.append('case_id', caseId);
        const result = await api('/assistant/parse-files', { method: 'POST', body: form });
        const parsed = result.files[0];
        if (!attached.has(parsed.id)) {
          combinedCharacters += parsed.characters;
          if (combinedCharacters > 150000)
            throw new Error(
              'Combined extracts exceed 150,000 characters. Remove a file and try again.',
            );
          attached.add(parsed.id);
        }
        if (epoch === generation.current) {
          setAttachments((previous) =>
            previous.some((item) => item.id === parsed.id) ? previous : [...previous, parsed],
          );
          setNotice(
            `${parsed.duplicate ? 'Reused the existing extract for' : 'Received and parsed'} ${parsed.name}. ${parsed.notice}`,
          );
        }
      }
    } catch (cause) {
      if (epoch === generation.current) setError(cause.message);
    } finally {
      if (epoch === generation.current) setUploading(false);
      if (fileInput.current) fileInput.current.value = '';
    }
  }
  async function saveReply(message, target) {
    const epoch = generation.current;
    await api('/assistant/case-evidence', {
      method: 'POST',
      body: {
        log_id: message.id,
        case_id: target,
        query_hash: message.query_hash,
        receipt: message.receipt,
      },
    });
    if (epoch !== generation.current) return;
    setMessages((previous) =>
      previous.map((entry) => (entry.id === message.id ? { ...entry, saved: true } : entry)),
    );
    if (caseId) setEvidence(await api(`${root}/evidence?case_id=${encodeURIComponent(caseId)}`));
    setNotice('Answer and sources saved as supporting research.');
  }
  async function hideEvidence(entry) {
    await api(`${root}/evidence/${entry.id}/visibility`, { method: 'PUT', body: { hidden: true } });
    setEvidence((previous) => previous.filter((item) => item.id !== entry.id));
    setMessages((previous) =>
      previous.map((message) =>
        message.id === (entry.response_id || entry.id) ? { ...message, saved: false } : message,
      ),
    );
    toast('Removed from supporting research', {
      duration: 5000,
      action: {
        label: 'Undo',
        onClick: () =>
          api(`${root}/evidence/${entry.id}/visibility`, { method: 'PUT', body: { hidden: false } })
            .then(() => api(`${root}/evidence?case_id=${encodeURIComponent(caseId)}`))
            .then(setEvidence)
            .catch((cause) => toast.error(cause.message)),
      },
    });
  }
  const history = messages.filter(
    (entry) =>
      entry.role === 'assistant' &&
      !entry.pending &&
      entry.question &&
      `${entry.question} ${entry.text}`.toLowerCase().includes(search.toLowerCase()),
  );
  const chips = caseId
    ? [...caseChips, 'What just happened?']
    : page === 'insights'
      ? [
          'Summarise this period',
          'Why are cases taking longer?',
          'Which providers are selected most?',
        ]
      : page === 'queue'
        ? ['What needs attention today?', 'Show blocked cases', 'Which cases are overdue?']
        : workspaceChips;
  const answers = messages.filter((message) => message.id && !message.pending);
  const latest = answers.at(-1);
  const canReveal = Boolean(!caseId || context?.medical_access_expires);
  const visibleMessages = messages.map((message) =>
    message.protected && !canReveal
      ? {
          ...message,
          text: 'Verify access in the digital client file to read this protected research.',
          sources: [],
          locked: true,
        }
      : message,
  );
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
        <span className="assistant-mode">Local demo replies</span>{' '}
        {caseId
          ? `For ${context?.client || 'this client'} · ${context?.state?.replaceAll('_', ' ').toLowerCase() || 'case records'}`
          : 'Using your accessible saved workspace records.'}
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
        <button
          className="button small"
          disabled={!messages.length}
          onClick={() => {
            if (
              !window.confirm(
                'Clear this conversation? Saved case research stays in its digital file.',
              )
            )
              return;
            generation.current += 1;
            controller.current?.abort();
            working.current = false;
            setBusy(false);
            setUploading(false);
            setAttachments([]);
            dictation.stop(true);
            speaker.stop();
            setMessages([]);
            setQuestion('');
            setNotice('Conversation cleared on this browser.');
          }}
        >
          <Trash2 size={14} />
          Clear conversation
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
                    body: {
                      log_ids: answers.map((message) => message.id),
                      format,
                      receipts: Object.fromEntries(
                        answers.map((message) => [message.id, message.receipt]),
                      ),
                    },
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
          <label htmlFor={`${id}-history`}>Search recent replies in this session</label>
          <input
            id={`${id}-history`}
            value={search}
            maxLength={1500}
            onChange={(event) => setSearch(event.target.value)}
          />
          {history.filter((entry) => !entry.protected || canReveal).length ? (
            history
              .filter((entry) => !entry.protected || canReveal)
              .map((entry) => (
                <div key={entry.id}>
                  <button
                    className="text-button"
                    disabled={busy}
                    onClick={() => ask(entry.question)}
                  >
                    {entry.question}
                  </button>
                  <small>
                    {new Date(entry.timestamp).toLocaleString('en-GB')} · {entry.confidence}
                  </small>
                  <details>
                    <summary>Saved answer</summary>
                    <AssistantCitations
                      text={entry.text || entry.answer || ''}
                      sources={entry.sources}
                      caseId={caseId}
                    />
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
          <h4>Supporting research</h4>
          {evidence.length ? (
            evidence
              .filter((entry) => !entry.protected || canReveal)
              .map((entry) => (
                <details key={entry.id}>
                  <summary>{entry.question}</summary>
                  <AssistantCitations text={entry.answer} sources={entry.sources} caseId={caseId} />
                  <small>
                    {entry.timestamp} · {entry.model_version}
                  </small>
                  <button
                    className="text-button"
                    aria-label={`Remove research: ${entry.question}`}
                    onClick={() => act(() => hideEvidence(entry))}
                  >
                    <Trash2 size={14} />
                    Remove
                  </button>
                </details>
              ))
          ) : (
            <p>No assistant answers saved yet. Use Save to evidence on an answer.</p>
          )}
        </div>
      )}
      <div className="assistant-suggestions">
        {!question.trim() &&
          chips.map((text) => (
            <button
              key={text}
              className="button small"
              disabled={!storageReady || busy || uploading}
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
        {visibleMessages.map((message, index) => (
          <article className={`assistant-message ${message.role}`} key={message.id || index}>
            <strong>
              {message.role === 'broker'
                ? 'You'
                : caseId
                  ? 'Helm Case Assistant'
                  : 'Helm Workspace Assistant'}
            </strong>
            <AssistantCitations
              text={message.text || 'Reading the saved records…'}
              sources={message.sources}
              caseId={caseId}
            />
            {speaker.id === message.id && speaker.status !== 'idle' && (
              <div className="assistant-reading-line" aria-hidden="true">
                <span style={{ transform: `scaleX(${speaker.progress})` }} />
              </div>
            )}
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
            {message.id && !message.pending && !message.locked && (
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
                  {
                    <button
                      className="button small"
                      disabled={message.saved}
                      onClick={() =>
                        caseId ? act(() => saveReply(message, caseId)) : setSavingMessage(message)
                      }
                    >
                      {message.saved ? <Check size={14} /> : <Bookmark size={14} />}
                      {message.saved ? 'Saved to evidence' : 'Save to evidence'}
                    </button>
                  }
                  {speechAvailable && (
                    <button
                      className="button small"
                      onClick={() => speaker.speak(message.text, message.id)}
                    >
                      <Volume2 size={14} />
                      Listen
                    </button>
                  )}
                  {caseId && (
                    <button
                      className="button small"
                      onClick={() =>
                        act(async () => {
                          const link = await api(`${root}/${message.id}/share`, {
                            method: 'POST',
                            body: { receipt: message.receipt },
                          });
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
      {speaker.status !== 'idle' && (
        <div className="assistant-audio-controls" aria-label="Read aloud controls">
          <button
            className="button small"
            onClick={speaker.status === 'paused' ? speaker.resume : speaker.pause}
          >
            {speaker.status === 'paused' ? <Play size={14} /> : <Pause size={14} />}{' '}
            {speaker.status === 'paused' ? 'Resume reading' : 'Pause reading'}
          </button>
          <button className="button small" onClick={speaker.stop}>
            <Square size={14} />
            Stop reading
          </button>
          <label>
            Reading speed
            <select
              value={speaker.rate}
              onChange={(event) => speaker.changeRate(Number(event.target.value))}
            >
              {[0.75, 1, 1.25, 1.5].map((rate) => (
                <option value={rate} key={rate}>
                  {rate}×
                </option>
              ))}
            </select>
          </label>
        </div>
      )}
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
            disabled={!storageReady || dictation.state === 'transcribing'}
            onChange={(event) => {
              if (dictation.state !== 'idle') dictation.stop(true);
              setQuestion(event.target.value);
            }}
            placeholder={
              caseId
                ? 'For example: Why is Northgate ranked first?'
                : 'For example: What needs attention today?'
            }
          />
          <button
            className="button primary"
            disabled={
              !storageReady || busy || uploading || dictation.state !== 'idle' || !question.trim()
            }
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
            accept=".pdf,.docx,.xlsx,.xls,.csv,.png,.jpg,.jpeg,.webp,.tif,.tiff,.txt,.md,.json,.mp3,.wav,.m4a,.webm"
            hidden
            onChange={(event) => upload([...event.target.files])}
          />
          <button
            type="button"
            className="button small"
            disabled={!storageReady || uploading || busy}
            onClick={() => fileInput.current?.click()}
          >
            <Paperclip size={16} />
            {uploading ? 'Parsing locally…' : 'Attach files'}
          </button>
          <button
            type="button"
            className={`button small ${dictation.state !== 'idle' ? 'assistant-recording' : ''}`}
            disabled={
              !dictation.available ||
              busy ||
              uploading ||
              dictation.state === 'transcribing' ||
              (!(window.SpeechRecognition || window.webkitSpeechRecognition) &&
                !capabilities?.speech_available)
            }
            aria-pressed={dictation.state === 'listening' || dictation.state === 'recording'}
            onClick={() => dictation.start(question)}
          >
            <Mic size={16} />
            {dictation.state === 'transcribing'
              ? 'Transcribing…'
              : dictation.state !== 'idle'
                ? 'Stop recording'
                : 'Voice input'}
          </button>
        </div>
        <small className="muted">
          {dictation.state !== 'idle' && (
            <span className="assistant-voice-status" role="status">
              <span aria-hidden="true" className="assistant-voice-bars">
                <i />
                <i />
                <i />
                <i />
              </span>
              {dictation.state === 'transcribing'
                ? 'Transcribing locally…'
                : dictation.state === 'recording'
                  ? 'Recording for local transcription…'
                  : 'Listening…'}
            </span>
          )}
          Drop files here · Up to 5 files, 25 MB each · 150,000 extracted characters combined. Voice
          uses your browser’s speech service first, with local transcription as a fallback. Review
          the transcript before sending. Case document analysis requires verified medical access.
        </small>
        {attachments.map((file) => (
          <div className="assistant-attachment" key={file.id}>
            <span>
              {file.name}
              {file.pages ? ` · ${file.pages} pages` : ''} ·{' '}
              {file.characters?.toLocaleString('en-GB')} characters
              {file.truncated ? ' · extract limited to 50,000 characters' : ''}
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
            {file.preview && (
              <details className="assistant-file-preview">
                <summary>Preview {file.name}</summary>
                <p>{file.preview}</p>
              </details>
            )}
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
      <p className="assistant-boundary">This assistant cannot select policies or approve advice.</p>
      {savingMessage && (
        <AssistantCasePicker
          onClose={() => setSavingMessage(null)}
          onSelect={(target) => saveReply(savingMessage, target)}
        />
      )}
    </section>
  );
}

export function AssistantLauncher() {
  useEffect(() => {
    window.dispatchEvent(new CustomEvent('helm:assistant-open'));
  }, []);
  return (
    <p className="muted">
      Your assistant opens beside this client file.{' '}
      <button
        className="text-button"
        onClick={() => window.dispatchEvent(new CustomEvent('helm:assistant-open'))}
      >
        Open assistant
      </button>
    </p>
  );
}

export function AssistantDock() {
  const [open, setOpen] = useState(false),
    [instant, setInstant] = useState(false);
  const host = usePanelHost(true),
    reduced = useReducedMotion(),
    user = useSessionStore((state) => state.user),
    trigger = useRef(null),
    wasOpen = useRef(false);
  const x = useMotionValue(0),
    y = useMotionValue(0),
    positionKey = `helm-assistant-position:${user.id}`;
  function constrain(a, b) {
    if (window.innerWidth < 640) return [0, 0];
    return [
      Math.max(
        -(window.innerWidth - 24 - (trigger.current?.offsetWidth || 184) - 12),
        Math.min(12, a),
      ),
      Math.max(
        -(window.innerHeight - 24 - (trigger.current?.offsetHeight || 48) - 12),
        Math.min(12, b),
      ),
    ];
  }
  useEffect(() => {
    try {
      const stored = JSON.parse(localStorage.getItem(positionKey) || 'null');
      if (stored && Number.isFinite(stored.x) && Number.isFinite(stored.y)) {
        const [a, b] = constrain(stored.x, stored.y);
        x.set(a);
        y.set(b);
      }
    } catch {
      /* Optional position preference. */
    }
    const resize = () => {
      const [a, b] = constrain(x.get(), y.get());
      x.set(a);
      y.set(b);
    };
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, [positionKey, x, y]);
  const drag = useDrag(
    ({ offset: [a, b], last, tap }) => {
      const [nextX, nextY] = constrain(a, b);
      x.set(nextX);
      y.set(nextY);
      if (last && !tap)
        try {
          localStorage.setItem(positionKey, JSON.stringify({ x: nextX, y: nextY }));
        } catch {
          /* Optional preference. */
        }
    },
    { from: () => [x.get(), y.get()], filterTaps: true, enabled: !open },
  );
  const location = useLocation(),
    navigate = useNavigate(),
    origin = useRef(null);
  const caseId = caseIdFromPath(location.pathname);
  useEffect(() => {
    function show(event) {
      origin.current = document.activeElement;
      setInstant(Boolean(event.detail?.keyboard));
      setOpen(true);
    }
    function shortcut(event) {
      if ((event.ctrlKey || event.metaKey) && !event.shiftKey && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        window.dispatchEvent(
          new CustomEvent('helm:assistant-open', { detail: { keyboard: true } }),
        );
      }
    }
    window.addEventListener('helm:assistant-open', show);
    window.addEventListener('keydown', shortcut);
    const tasks = () => setOpen(false);
    window.addEventListener('helm:tasks-open', tasks);
    return () => {
      window.removeEventListener('helm:assistant-open', show);
      window.removeEventListener('keydown', shortcut);
      window.removeEventListener('helm:tasks-open', tasks);
    };
  }, []);
  useEffect(() => {
    if (wasOpen.current && !open) {
      if (origin.current?.isConnected) origin.current.focus();
      else trigger.current?.focus();
    }
    wasOpen.current = open;
  }, [open]);
  function close() {
    setOpen(false);
  }
  useEffect(() => {
    if (!open) return;
    function escape(event) {
      if (
        event.key === 'Escape' &&
        !document.querySelector(
          '[data-helm-popover][data-state="open"],dialog.assistant-picker[open]',
        )
      ) {
        event.preventDefault();
        event.stopPropagation();
        setOpen(false);
      }
    }
    document.addEventListener('keydown', escape, true);
    return () => document.removeEventListener('keydown', escape, true);
  }, [open]);
  if (!host) return null;
  return createPortal(
    <>
      {!open && (
        <motion.button
          {...drag()}
          ref={trigger}
          className="assistant-ask-pill"
          style={{ x, y, touchAction: 'none' }}
          aria-label="Ask Helm workspace assistant"
          aria-expanded={open}
          onClick={() => window.dispatchEvent(new CustomEvent('helm:assistant-open'))}
        >
          <MessageSquare size={18} />
          Ask Helm <kbd>⌘ / Ctrl K</kbd>
        </motion.button>
      )}
      {open && (
        <motion.aside
          className="assistant-dock"
          aria-label="Pinned assistant panel"
          onKeyDown={keepPanelFocus}
          initial={instant || reduced ? false : { x: 16, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          transition={
            instant || reduced ? { duration: 0 } : { type: 'spring', stiffness: 380, damping: 30 }
          }
        >
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
        </motion.aside>
      )}
    </>,
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
          <AssistantCitations text={data.answer} sources={data.sources} caseId={data.case_id} />
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
