import React, { useState } from 'react';
import BottomSheet from './BottomSheet';
import TextArea from './TextArea';
import { api } from '../api';

export default function CloseWithoutAdvice({ item, ratings, container, onClosed }) {
  const [open, setOpen] = useState(false),
    [reason, setReason] = useState(''),
    [confirmed, setConfirmed] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const plans = item.ranking?.top || [];
  if (!plans.length || !plans.every(({ plan }) => ratings[plan.id]?.decision === 'NO')) return null;
  async function close(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api(`/cases/${item.id}/close-without-advice`, {
        method: 'POST',
        body: { ranking_id: item.ranking.id, reason: reason.trim(), confirmed },
      });
      setOpen(false);
      await onClosed();
    } catch (cause) {
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="notice warning">
        <div>
          <h3>No suitable plans</h3>
          <p>
            You excluded every plan. Record the outcome and close this comparison without sending a
            recommendation.
          </p>
          <button className="button" onClick={() => setOpen(true)}>
            Close without advice
          </button>
        </div>
      </div>
      <BottomSheet
        open={open}
        onClose={() => !busy && setOpen(false)}
        container={container}
        title="Close without sending advice"
        description="This closes the case and cancels pending agent work. Your assessments and reason stay in the evidence record."
      >
        <form onSubmit={close}>
          <TextArea
            label="Reason for no suitable recommendation"
            value={reason}
            minLength={20}
            maxLength={2000}
            required
            onChange={(event) => setReason(event.target.value)}
          />
          <label className="check-row">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            I confirm all plans are unsuitable and no recommendation should be sent.
          </label>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <button
            className="button primary"
            disabled={busy || !confirmed || reason.trim().length < 20}
          >
            {busy ? 'Recording…' : 'Confirm closure'}
          </button>
        </form>
      </BottomSheet>
    </>
  );
}
