import React, { useEffect, useRef, useState } from 'react';
import {
  CheckCheck,
  Circle,
  Clock3,
  FileSearch,
  MessageSquare,
  Send,
  ShieldCheck,
} from 'lucide-react';
import { api, label, money } from '../api';

export function useCaseWorkspace(item) {
  const [data, setData] = useState(null),
    [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    api(`/cases/${item.id}/workspace`)
      .then((value) => {
        if (active) {
          setData(value);
          setError('');
        }
      })
      .catch((cause) => {
        if (active) setError(cause.message);
      });
    return () => {
      active = false;
    };
  }, [item.id, item.version, item.events?.length]);
  return { data, error };
}

export function AgentWork({ data, detailed = false }) {
  if (!data) return <p className="muted">Loading saved agent work…</p>;
  return (
    <section className="agent-work" aria-label="Agent work and reasons">
      <div className="section-header">
        <h3>Five agents. Every step explained.</h3>
        <span className="subtle-badge">LIVE SAVED WORK</span>
      </div>
      <p className="muted">{data.next_action}</p>
      <ol className="agent-work-list">
        {data.agent_work.map((agent) => {
          const Icon =
            agent.status === 'complete' ? CheckCheck : agent.status === 'running' ? Clock3 : Circle;
          return (
            <li key={agent.id} className={`agent-work-item ${agent.status}`}>
              <Icon size={21} aria-hidden="true" />
              <div>
                <div className="agent-work-heading">
                  <strong>
                    Agent {agent.id} · {agent.name}
                  </strong>
                  <span>{label(agent.status)}</span>
                </div>
                <p>{agent.summary}</p>
                <details open={detailed || undefined}>
                  <summary>Why this agent works on the case</summary>
                  <p>{agent.why}</p>
                  {agent.evidence && (
                    <p className="evidence-reference">
                      Saved {label(agent.evidence.kind)} · version {agent.evidence.version}
                      <br />
                      <code>{agent.evidence.hash}</code>
                    </p>
                  )}
                  {agent.finished_at && (
                    <small>Saved {new Date(agent.finished_at).toLocaleString('en-GB')}</small>
                  )}
                </details>
              </div>
            </li>
          );
        })}
      </ol>
      {detailed && (
        <>
          <p className="audit-verification">
            <ShieldCheck size={16} />
            Audit chain {data.chain_valid ? 'verified' : 'verification failed'} ·{' '}
            {data.events.length} events
          </p>
          <ol className="readable-audit">
            {data.events.map((event) => (
              <li key={event.seq}>
                <div>
                  <strong>{label(event.type)}</strong>
                  <span>
                    {event.actor.startsWith('broker:')
                      ? 'Human broker decision'
                      : event.actor.startsWith('agent:')
                        ? label(event.actor.replace(':', ' '))
                        : event.actor === 'demo-automation'
                          ? 'Automatic demo preparation'
                          : 'System'}
                  </span>
                </div>
                <time dateTime={event.created_at}>
                  {new Date(event.created_at).toLocaleString('en-GB')}
                </time>
                {event.payload.why && <p>{event.payload.why}</p>}
                {event.payload.reason && (
                  <p>
                    Reason: {label(event.payload.reason)}
                    {event.payload.code ? ` · ${event.payload.code}` : ''}
                  </p>
                )}
                {[1, 2].includes(event.payload.decision) && (
                  <p>Human decision {event.payload.decision} of 2</p>
                )}
                <small>
                  Event #{event.seq} · <code>{event.hash}</code>
                </small>
              </li>
            ))}
          </ol>
        </>
      )}
    </section>
  );
}

export function DigitalClientFile({ data }) {
  if (!data) return <p className="muted">Opening the digital client file…</p>;
  const file = data.client_file,
    needs = file.preferences;
  return (
    <section className="digital-client-file" aria-labelledby="digital-file-title">
      <div className="section-header">
        <h3 id="digital-file-title">Digital client file</h3>
        <FileSearch size={21} />
      </div>
      <p className="muted">
        One case record of the information received, preferences, documents and decisions. Fields
        without source information are marked “Not provided”.
      </p>
      <dl className="client-facts-grid">
        {Object.entries({
          Name: file.identity.name,
          'Cover type': label(file.identity.cover_type),
          'Postcode district': file.identity.postcode,
          'Date of birth': file.identity.date_of_birth,
          'Contact details': file.identity.contact_details,
          'Sharing consent':
            file.consent_to_share == null
              ? null
              : file.consent_to_share
                ? 'Recorded'
                : 'Not recorded',
        }).map(([key, value]) => (
          <div key={key}>
            <dt>{key}</dt>
            <dd>{value || 'Not provided'}</dd>
          </div>
        ))}
      </dl>
      <section className="file-section">
        <h4>Preferences and priorities</h4>
        <dl className="client-facts-grid">
          <div>
            <dt>Annual budget</dt>
            <dd>{needs.budget_annual_pence ? money(needs.budget_annual_pence) : 'Not provided'}</dd>
          </div>
          <div>
            <dt>Hard budget cap</dt>
            <dd>{needs.hard_budget_cap ? money(needs.hard_budget_cap) : 'Not provided'}</dd>
          </div>
          <div>
            <dt>Priority order</dt>
            <dd>{needs.priorities?.map(label).join(' → ') || 'Not provided'}</dd>
          </div>
          <div>
            <dt>Hospital list level</dt>
            <dd>{needs.hospital_level ?? 'Not provided'}</dd>
          </div>
          <div>
            <dt>Preferred underwriting</dt>
            <dd>{label(needs.preferred_underwriting) || 'Not provided'}</dd>
          </div>
        </dl>
        <ul>
          {Object.entries(needs.coverage || {}).map(([name, need]) => (
            <li key={name}>
              {label(name)} · requested level {need.level}
              {need.must_have ? ' · must have' : ''}
            </li>
          ))}
        </ul>
      </section>
      <section className="file-section">
        <h4>Medical declaration</h4>
        <p>
          {file.medical_declaration_count} statements received. {file.medical_notice}
        </p>
        <p>Previous clinical records: not supplied to this case.</p>
      </section>
      {file.missing.length > 0 && (
        <p className="notice warning">Missing: {file.missing.map(label).join(', ')}</p>
      )}
      <section className="file-section">
        <h4>Source facts</h4>
        {Object.entries(file.facts).map(([key, fact]) => (
          <div className="source-fact" key={key}>
            <strong>
              {label(key)}:{' '}
              {typeof fact.value === 'object' ? JSON.stringify(fact.value) : String(fact.value)}
            </strong>
            <small>
              Source: {fact.source} ·{' '}
              {fact.verified_by ? 'Broker verified' : 'Source extraction; review at sign-off'}
            </small>
          </div>
        ))}
        {file.source && (
          <details>
            <summary>Original request reference</summary>
            <code>{file.source.hash}</code>
            <p>{file.identity.request_reference}</p>
          </details>
        )}
      </section>
      <section className="file-section">
        <h4>Documents and saved records</h4>
        {file.documents.length ? (
          <ul>
            {file.documents.map((document) => (
              <li key={document.id}>
                {label(document.category)} · {document.pages} pages ·{' '}
                {new Date(document.created_at).toLocaleDateString('en-GB')}
                <small className="block">
                  Sensitive contents require verified access in the fact-find.
                </small>
              </li>
            ))}
          </ul>
        ) : (
          <p>No source documents were uploaded. The original structured request is saved below.</p>
        )}
        <ol className="file-records">
          {file.records.map((record) => (
            <li key={`${record.kind}-${record.version}`}>
              <strong>
                {label(record.kind)} · v{record.version}
              </strong>
              <time dateTime={record.created_at}>
                {new Date(record.created_at).toLocaleString('en-GB')}
              </time>
              <code>{record.hash}</code>
            </li>
          ))}
        </ol>
      </section>
      {file.selected_policies.length > 0 && (
        <section className="file-section">
          <h4>Broker’s selected order</h4>
          <ol>
            {file.selected_policies.map((plan) => (
              <li key={plan.id}>
                {plan.name} · {money(plan.annual_pence)}/year
              </li>
            ))}
          </ol>
        </section>
      )}
      <section className="file-section">
        <h4>Delivery and response</h4>
        <p>
          {file.publication
            ? 'A recommendation delivery record is saved.'
            : 'No delivery recorded yet.'}{' '}
          {file.consumer_response
            ? 'A consumer response has been recorded.'
            : 'No consumer response recorded.'}
        </p>
      </section>
    </section>
  );
}

export function CaseAssistant({ caseId, onNavigate, onOpenCase }) {
  const [messages, setMessages] = useState([]),
    [question, setQuestion] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const end = useRef(null),
    generation = useRef(0);
  useEffect(() => {
    generation.current += 1;
    setMessages([]);
    setQuestion('');
    setError('');
  }, [caseId]);
  async function ask(value) {
    if (busy || !value.trim()) return;
    const epoch = generation.current;
    setBusy(true);
    setError('');
    setQuestion('');
    setMessages((previous) => [...previous, { role: 'broker', text: value }].slice(-40));
    try {
      const response = await api('/workspace/assistant', {
        method: 'POST',
        body: { case_id: caseId || null, question: value },
      });
      if (epoch === generation.current)
        setMessages((previous) =>
          [
            ...previous,
            { role: 'assistant', text: response.answer, sources: response.sources },
          ].slice(-40),
        );
    } catch (cause) {
      if (epoch === generation.current) setError(cause.message);
    } finally {
      setBusy(false);
      end.current?.scrollIntoView({ block: 'nearest' });
    }
  }
  return (
    <section
      className="case-assistant"
      aria-labelledby={caseId ? 'case-assistant-title' : 'workspace-assistant-title'}
    >
      <div className="section-header">
        <h3 id={caseId ? 'case-assistant-title' : 'workspace-assistant-title'}>
          <MessageSquare size={19} />
          {caseId ? 'Your case assistant' : 'Your workspace assistant'}
        </h3>
        <span className="subtle-badge">SAVED EVIDENCE</span>
      </div>
      <p className="muted">
        {caseId
          ? 'Ask about this client, policy comparisons, agent work, documents or the next step.'
          : 'See your accessible cases and what needs attention. Open a case for detailed answers.'}{' '}
        Answers use local saved records. This assistant cannot select policies or approve advice.
      </p>
      <div className="assistant-suggestions">
        {(caseId
          ? [
              'What should I do next?',
              'What are the client’s preferences?',
              'Why this ranking?',
              'What did each agent do?',
            ]
          : ['Summarise my workspace']
        ).map((text) => (
          <button key={text} className="button small" disabled={busy} onClick={() => ask(text)}>
            {text}
          </button>
        ))}
      </div>
      <div
        className="assistant-messages"
        role="log"
        aria-label="Assistant conversation"
        aria-live="polite"
      >
        {messages.map((message, index) => (
          <article className={`assistant-message ${message.role}`} key={index}>
            <strong>{message.role === 'broker' ? 'You' : 'Case assistant'}</strong>
            <p>{message.text}</p>
            {message.sources?.map((source, i) => (
              <button
                className="text-button"
                key={i}
                onClick={() =>
                  source.case_id ? onOpenCase?.(source.case_id) : onNavigate?.(source.view)
                }
              >
                {source.label}
              </button>
            ))}
          </article>
        ))}
        {busy && <p>Reading the saved records…</p>}
        <div ref={end} />
      </div>
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
        <label htmlFor={caseId ? 'case-question' : 'workspace-question'}>
          Ask {caseId ? 'about this case' : 'about your workspace'}
        </label>
        <div>
          <input
            id={caseId ? 'case-question' : 'workspace-question'}
            value={question}
            maxLength={1500}
            required
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="For example: Why is Northgate ranked first?"
          />
          <button
            className="button primary"
            disabled={busy || !question.trim()}
            aria-label="Send question"
          >
            <Send size={18} />
          </button>
        </div>
      </form>
    </section>
  );
}

export default function CaseIntelligence({ item, view, onNavigate }) {
  const { data, error } = useCaseWorkspace(item);
  return (
    <>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {view === 'file' ? (
        <DigitalClientFile data={data} />
      ) : view === 'assistant' ? (
        <CaseAssistant caseId={item.id} onNavigate={onNavigate} />
      ) : (
        <AgentWork data={data} detailed />
      )}
    </>
  );
}
