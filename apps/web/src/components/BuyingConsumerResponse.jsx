import React, { useState } from 'react';
import { api } from '../api';

export default function BuyingConsumerResponse({ item, document, onChanged }) {
  const [note, setNote] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  if (!['ipid', 'toba'].includes(document.doc_type)) return null;
  async function respond(decision) {
    setBusy(true);
    setError('');
    try {
      await api(`/policy-buying/cases/${item.case_id}/documents/${document.doc_type}/respond`, {
        method: 'POST',
        body: { expected_version: item.version, document_id: document.id, decision, note },
      });
      await onChanged();
    } catch (cause) {
      setError(cause.message);
      onChanged();
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      {document.doc_type === 'ipid' && item.consumer_query && (
        <p className="notice warning">Consumer query: {item.consumer_query}</p>
      )}
      {document.status === 'sent' && (
        <div className="pb-demo">
          <h4>Demo consumer response</h4>
          <button className="button small" disabled={busy} onClick={() => respond('confirm')}>
            Simulate: consumer confirms
          </button>
          {document.doc_type === 'ipid' && (
            <>
              <label>
                Consumer correction request
                <textarea
                  value={note}
                  maxLength={2000}
                  onChange={(event) => setNote(event.target.value)}
                />
              </label>
              <button
                className="button small"
                disabled={busy || !note.trim()}
                onClick={() => respond('change')}
              >
                Simulate: consumer requests a change
              </button>
            </>
          )}
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
        </div>
      )}
    </>
  );
}
