import React, { useState } from 'react';
import { api } from '../api';

function actorLabel(actor) {
  if (actor.startsWith('demo-consumer:')) return 'Demo consumer';
  if (actor.startsWith('broker:')) return 'Broker';
  return actor === 'demo-agent' ? 'Local demo agent' : actor;
}

export default function BuyingFeed({ item, onRead }) {
  const [error, setError] = useState('');
  async function read() {
    try {
      await api(`/policy-buying/cases/${item.case_id}/read`, {
        method: 'POST',
        body: { seq: item.latest_seq },
      });
      onRead();
    } catch (cause) {
      setError(cause.message);
    }
  }
  return (
    <aside className="pb-updates" aria-label="Case updates and communication">
      <h2>Case updates</h2>
      <p>{item.updates} unread updates</p>
      <button className="button small" disabled={!item.updates} onClick={read}>
        Mark updates read
      </button>
      <button
        className="button small"
        onClick={() => window.dispatchEvent(new CustomEvent('helm:assistant-open'))}
      >
        Ask assistant about this case
      </button>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <ol className="pb-feed">
        {item.feed.map((event) => (
          <li key={event.seq}>
            <p>{event.message}</p>
            <small>
              {actorLabel(event.actor)} ·{' '}
              <time dateTime={event.created_at}>
                {new Date(event.created_at).toLocaleString('en-GB')}
              </time>
            </small>
          </li>
        ))}
      </ol>
      <details>
        <summary>Communication thread</summary>
        <ol className="pb-feed">
          {[...item.feed]
            .reverse()
            .filter((event) => /sent|consumer|completed|broker_edit/.test(event.type))
            .map((event) => (
              <li key={event.seq}>
                <p>{event.message}</p>
                <small>
                  #{event.seq} · {actorLabel(event.actor)}
                </small>
              </li>
            ))}
        </ol>
      </details>
      <details>
        <summary>Document version history</summary>
        <ul>
          {item.history.map((document) => (
            <li key={document.id}>
              <a
                className="button small"
                href={`/api/v1/policy-buying/cases/${item.case_id}/documents/${document.id}.pdf`}
                download
              >
                {document.doc_type.replaceAll('_', ' ')} · v{document.version}
              </a>{' '}
              · {document.edited_by_broker ? 'Broker edited' : 'Demo agent draft'}
            </li>
          ))}
        </ul>
      </details>
    </aside>
  );
}
