import React, { useState } from 'react';
import { api } from '../api';
import TextArea from './TextArea';

export default function MedicalReview({ item, revealed, onSaved }) {
  const [decision, setDecision] = useState('record_declared'),
    [reason, setReason] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      onSaved(
        await api(`/cases/${item.id}/medical-review`, {
          method: 'POST',
          body: { decision, reason: reason.trim() },
        }),
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="medical-review-form" onSubmit={submit}>
      <h3>H5 · Review medical wording</h3>
      <p>{item.medical_triage.message}</p>
      <p className="muted">
        Reveal and review the original statement first. This records your interpretation;
        underwriting and exclusions remain subject to insurer confirmation.
      </p>
      <label>
        Review outcome
        <select value={decision} onChange={(e) => setDecision(e.target.value)}>
          <option value="record_declared">Record as a declared statement</option>
          <option value="no_ambiguity">Wording reviewed; proceed without inference</option>
          <option value="seek_clarification">Request clarification from the consumer</option>
        </select>
      </label>
      <TextArea
        label="Medical wording review reason"
        required
        minLength={30}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
      />
      {!revealed && (
        <p role="status">Verify your identity and reveal the medical statement to continue.</p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <button
        className="button primary small"
        disabled={!revealed || busy || reason.trim().length < 30}
      >
        {busy ? 'Recording…' : 'Record medical review'}
      </button>
    </form>
  );
}
