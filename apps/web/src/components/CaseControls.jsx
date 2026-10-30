import React, { useState } from 'react';
import { api, label } from '../api';
import BottomSheet from './BottomSheet';
import TextArea from './TextArea';

export default function CaseControls({ item, user, container, onSaved }) {
  const [open, setOpen] = useState(false),
    [operation, setOperation] = useState('priority'),
    [assignees, setAssignees] = useState([]),
    [assignee, setAssignee] = useState(user.id),
    [priority, setPriority] = useState(item.priority),
    [reason, setReason] = useState(''),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  async function show() {
    setError('');
    setReason('');
    setPriority(item.priority);
    try {
      setAssignees(await api('/case-controls/assignees'));
      setOpen(true);
    } catch (cause) {
      setError(cause.message);
    }
  }
  async function save(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api(`/cases/${item.id}/controls`, {
        method: 'POST',
        body: {
          operation,
          expected_version: item.version,
          reason,
          assignee_id: assignee,
          priority,
        },
      });
      setOpen(false);
      await onSaved();
    } catch (cause) {
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <button className="text-button case-controls-trigger" onClick={show}>
        Case controls
      </button>
      {!open && error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <BottomSheet
        open={open}
        onClose={() => !busy && setOpen(false)}
        container={container}
        title="Case controls"
        description="Record why ownership or priority should change. Taking over a paused case leaves it paused until you review and resume it."
      >
        <form onSubmit={save}>
          <label>
            Change
            <select
              aria-label="Case control change"
              value={operation}
              onChange={(e) => setOperation(e.target.value)}
            >
              <option value="priority">Priority</option>
              <option value="assign">Assignment</option>
              {item.state === 'PAUSED_NEEDS_HUMAN' && (
                <option value="takeover">Take over paused case</option>
              )}
            </select>
          </label>
          {operation === 'priority' && (
            <label>
              Priority
              <select
                aria-label="Priority"
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
              >
                {['normal', 'urgent'].map((value) => (
                  <option key={value} value={value}>
                    {label(value)}
                  </option>
                ))}
              </select>
            </label>
          )}
          {operation === 'assign' && (
            <label>
              Assign to
              <select
                aria-label="Assign to"
                value={assignee}
                onChange={(e) => setAssignee(e.target.value)}
              >
                {assignees.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <TextArea
            label="Reason for changing case controls"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            minLength={20}
            required
          />
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <button className="button" disabled={busy || reason.trim().length < 20}>
            {busy ? 'Saving…' : 'Save case controls'}
          </button>
        </form>
      </BottomSheet>
    </>
  );
}
