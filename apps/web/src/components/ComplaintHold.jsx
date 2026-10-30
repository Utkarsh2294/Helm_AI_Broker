import React, { useState } from 'react';
import { api } from '../api';
import TextArea from './TextArea';

export default function ComplaintHold({ item, user, onResolved }) {
  const [resolution, setResolution] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  async function resolve(event) {
    event.preventDefault();
    setBusy(true);
    try {
      await api(`/cases/${item.id}/complaints/resolve`, {
        method: 'POST',
        body: { resolution: resolution.trim() },
      });
      await onResolved();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="notice warning">
      <div>
        <h3>Complaint hold</h3>
        <p>
          Agent work is paused for the designated compliance owner. The demo response deadline is{' '}
          {item.complaint?.due_at
            ? new Date(item.complaint.due_at).toLocaleString()
            : 'awaiting assignment'}
          .
        </p>
        {user.role === 'compliance_officer' && item.complaint?.owner_id === user.id && (
          <form onSubmit={resolve}>
            <TextArea
              label="Complaint resolution"
              minLength={20}
              required
              value={resolution}
              onChange={(e) => setResolution(e.target.value)}
            />
            {error && <p role="alert">{error}</p>}
            <button className="button" disabled={busy || resolution.trim().length < 20}>
              {busy ? 'Recording…' : 'Record resolution and release hold'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
