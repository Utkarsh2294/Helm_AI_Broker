import React, { useState } from 'react';
import { api } from '../api';
import StarRating from './StarRating';
import PlanDecisionButton from './PlanDecisionButton';
import TextArea from './TextArea';

export default function PlanAssessment({ caseId, rankingId, row, rating, onSaved, onDirty }) {
  const draft =
    row.ai_draft_text ||
    (typeof row.explanation === 'string' ? row.explanation : row.explanation.overall);
  const [stars, setStars] = useState(rating?.stars || null),
    [decision, setDecision] = useState(rating?.decision || null),
    [reason, setReason] = useState(rating?.reason_text || draft),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [dirty, setDirty] = useState(false);
  function change(update) {
    update();
    setDirty(true);
    onDirty(row.plan.id);
  }
  async function save(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const result = await api(`/cases/${caseId}/plans/${encodeURIComponent(row.plan.id)}/rating`, {
        method: 'POST',
        body: { ranking_id: rankingId, stars, decision, reason_text: reason },
      });
      setDirty(false);
      onSaved(result);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="plan-assessment" onSubmit={save} aria-label={`Assessment of ${row.plan.name}`}>
      <h4>Your assessment</h4>
      <StarRating
        label={`Suitability stars for ${row.plan.name}`}
        value={stars}
        onChange={(value) => change(() => setStars(value))}
      />
      <PlanDecisionButton value={decision} onChange={(value) => change(() => setDecision(value))} />
      <TextArea
        label={`Your reason for ${row.plan.name}`}
        minLength={20}
        maxLength={2000}
        required
        value={reason}
        onChange={(event) => change(() => setReason(event.target.value))}
      />
      {reason === draft && (
        <p className="notice warning">Reason appears unedited — add your own assessment.</p>
      )}
      {rating && !dirty && (
        <p role="status">
          Assessment saved · {rating.is_edited ? 'Broker edited' : 'Reason appears unedited'}
        </p>
      )}
      {dirty && <p role="status">Unsaved assessment</p>}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="button-row">
        <button
          className="button primary small"
          disabled={busy || !stars || !decision || reason.trim().length < 20 || (rating && !dirty)}
        >
          {busy ? 'Saving…' : 'Save rating'}
        </button>
        <button
          type="button"
          className="button small"
          disabled={busy}
          onClick={() => change(() => setReason(draft))}
        >
          Reset draft
        </button>
        <button
          type="button"
          className="button small"
          disabled={busy}
          onClick={() =>
            change(() => {
              setStars(null);
              setDecision(null);
              setReason('');
            })
          }
        >
          Clear assessment
        </button>
      </div>
    </form>
  );
}
