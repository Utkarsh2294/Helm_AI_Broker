import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { api } from '../api';
import { X } from 'lucide-react';

export default function AssistantCasePicker({ onSelect, onClose }) {
  const dialog = useRef(null),
    [query, setQuery] = useState(''),
    [cases, setCases] = useState([]),
    [selected, setSelected] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  useEffect(() => {
    dialog.current.showModal();
    const node = dialog.current;
    return () => node.close();
  }, []);
  useEffect(() => {
    let active = true;
    const timer = setTimeout(
      () =>
        api(`/cases?limit=50&q=${encodeURIComponent(query)}`)
          .then((data) => {
            if (active) setCases(data.items);
          })
          .catch((cause) => {
            if (active) setError(cause.message);
          }),
      180,
    );
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [query]);
  async function save(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await onSelect(selected);
      onClose();
    } catch (cause) {
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  }
  return createPortal(
    <dialog
      className="assistant-picker"
      ref={dialog}
      aria-labelledby="assistant-picker-title"
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onClose();
      }}
    >
      <form onSubmit={save}>
        <div className="section-header">
          <h2 id="assistant-picker-title">Save to a case</h2>
          <button
            className="icon-button"
            type="button"
            aria-label="Close case picker"
            disabled={busy}
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </div>
        <p>Choose an accessible digital client file for this supporting research.</p>
        <label htmlFor="assistant-case-search">Search cases</label>
        <input
          id="assistant-case-search"
          autoFocus
          value={query}
          maxLength={200}
          onChange={(event) => setQuery(event.target.value)}
        />
        <label htmlFor="assistant-case-choice">Case for saved research</label>
        <select
          id="assistant-case-choice"
          value={selected}
          required
          onChange={(event) => setSelected(event.target.value)}
        >
          <option value="">Choose a case…</option>
          {cases.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name} · {item.core_request_id || item.id.slice(0, 8)}
            </option>
          ))}
        </select>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div className="assistant-toolbar">
          <button className="button primary" disabled={!selected || busy}>
            {busy ? 'Saving…' : 'Save to evidence'}
          </button>
          <button className="button" type="button" disabled={busy} onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </dialog>,
    document.body,
  );
}
