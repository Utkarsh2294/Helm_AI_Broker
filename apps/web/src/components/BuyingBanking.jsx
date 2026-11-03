import React, { useEffect, useState } from 'react';
import { api } from '../api';
import Reauthenticate from './Reauthenticate';

export default function BuyingBanking({ item, onChanged }) {
  const [prompt, setPrompt] = useState(false),
    [raw, setRaw] = useState(null),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!raw) return;
    const timeout = setTimeout(() => setRaw(null), 30000);
    return () => clearTimeout(timeout);
  }, [raw]);
  if (item.stage !== 'AWAITING_BANKING_DETAILS') return null;
  const document = item.documents.find((row) => row.doc_type === 'banking_request');
  async function act(action) {
    setBusy(true);
    setError('');
    try {
      await api(`/policy-buying/cases/${item.case_id}/banking/${action}`, {
        method: 'POST',
        body: {
          expected_version: item.version,
          ...(action === 'complete' ? { document_id: document.id, confirm_signature: true } : {}),
        },
      });
      setRaw(null);
      await onChanged();
    } catch (cause) {
      setError(cause.message);
      onChanged();
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="pb-demo" aria-label="Fictional banking setup">
      <h3>Banking details</h3>
      <p>
        Only seeded dummy details are used. Annual payment matches the IPID. No live mandate is
        created.
      </p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!item.banking_received ? (
        <button
          className="button small"
          disabled={busy || !document}
          onClick={() => act('complete')}
        >
          Simulate: consumer submits banking details and mandate consent
        </button>
      ) : (
        <>
          <p>Fictional account ending 1234 · annual payment</p>
          <button className="button small" onClick={() => setPrompt(true)}>
            Open one-time banking verification
          </button>
          {prompt && (
            <Reauthenticate
              title="Verify to reveal fictional banking details once"
              actionLabel="Reveal dummy banking details"
              onVerified={async (proof) => {
                setRaw(
                  await api(`/policy-buying/cases/${item.case_id}/banking/reveal`, {
                    method: 'POST',
                    body: { expected_version: item.version },
                    headers: { 'X-Step-Up': proof },
                  }),
                );
                setPrompt(false);
                await onChanged();
              }}
            />
          )}{' '}
          {raw && (
            <div>
              <p>Fictional account holder: {raw.account_holder}</p>
              <p>Dummy sort code: {raw.sort_code}</p>
              <p>Dummy account number: {raw.account_number}</p>
              <p>This one-time view hides after 30 seconds.</p>
              <button className="button small" onClick={() => setRaw(null)}>
                Hide details
              </button>
            </div>
          )}
          <button className="button primary" disabled={busy} onClick={() => act('verify')}>
            Confirm fictional payment setup
          </button>
        </>
      )}
    </section>
  );
}
