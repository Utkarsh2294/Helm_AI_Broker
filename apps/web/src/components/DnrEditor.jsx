import React, { useEffect, useRef, useState } from 'react';
import { api, label } from '../api';
import Input from './Input';
import TextArea from './TextArea';

const criteria = [
  'affordability',
  'coverage',
  'network',
  'underwriting',
  'insurer_quality',
  'process_ease',
  'terms_clarity',
];

export default function DnrEditor({ item, onSaved, onClose }) {
  const [draft, setDraft] = useState(() => structuredClone(item.dnr));
  const version = useRef(item.dnr.version);
  const [reason, setReason] = useState(''),
    [saving, setSaving] = useState(false),
    [error, setError] = useState('');
  const payload = JSON.stringify(draft),
    [saved, setSaved] = useState(payload),
    failed = useRef('');
  const unique = new Set(draft.needs.priorities).size === draft.needs.priorities.length;
  const valid = reason.trim().length >= 3 && draft.needs.budget_annual_pence > 0 && unique;
  async function save() {
    if (!valid || saving || saved === payload) return;
    setSaving(true);
    setError('');
    try {
      const updated = await api(`/cases/${item.id}/dnr`, {
        method: 'PATCH',
        body: { dnr: { ...draft, version: version.current }, reason: reason.trim() },
      });
      version.current = updated.dnr.version;
      setSaved(payload);
      onSaved(updated);
    } catch (e) {
      failed.current = payload;
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }
  useEffect(() => {
    if (!valid || saving || saved === payload || failed.current === payload) return;
    const timer = setTimeout(save, 750);
    return () => clearTimeout(timer);
  }, [payload, reason, valid, saving, saved]);
  function change(key, value) {
    setDraft((current) => ({ ...current, needs: { ...current.needs, [key]: value } }));
  }
  function cover(key, field, value) {
    setDraft((current) => ({
      ...current,
      needs: {
        ...current.needs,
        coverage: {
          ...current.needs.coverage,
          [key]: { ...current.needs.coverage[key], [field]: value },
        },
      },
    }));
  }
  return (
    <form
      className="dnr-editor"
      onSubmit={(event) => {
        event.preventDefault();
        failed.current = '';
        save();
      }}
    >
      <h3>Edit stated requirements</h3>
      <p className="muted">
        Changes create a new sourced version and require a fresh sign-off. Medical statements retain
        their original wording.
      </p>
      <Input
        label="Annual budget (£)"
        type="number"
        min="1"
        step="0.01"
        required
        value={draft.needs.budget_annual_pence / 100}
        onChange={(e) => change('budget_annual_pence', Math.round(Number(e.target.value) * 100))}
      />
      <Input
        label="Hard budget cap (£), optional"
        type="number"
        min="1"
        step="0.01"
        value={draft.needs.hard_budget_cap === null ? '' : draft.needs.hard_budget_cap / 100}
        onChange={(e) =>
          change(
            'hard_budget_cap',
            e.target.value === '' ? null : Math.round(Number(e.target.value) * 100),
          )
        }
      />
      <label>
        Preferred underwriting
        <select
          value={draft.needs.preferred_underwriting}
          onChange={(e) => change('preferred_underwriting', e.target.value)}
        >
          {['moratorium', 'FMU'].map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
      </label>
      <fieldset>
        <legend>Acceptable underwriting options</legend>
        {['moratorium', 'FMU'].map((value) => (
          <label className="checkbox-label" key={value}>
            <input
              type="checkbox"
              checked={draft.needs.allowed_underwriting.includes(value)}
              onChange={(e) =>
                change(
                  'allowed_underwriting',
                  e.target.checked
                    ? [...draft.needs.allowed_underwriting, value]
                    : draft.needs.allowed_underwriting.filter((v) => v !== value),
                )
              }
            />
            {value}
          </label>
        ))}
      </fieldset>
      <label>
        Hospital network level
        <select
          value={draft.needs.hospital_level}
          onChange={(e) => change('hospital_level', Number(e.target.value))}
        >
          {[1, 2, 3].map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </label>
      <fieldset>
        <legend>Priority order</legend>
        {draft.needs.priorities.map((value, index) => (
          <label key={index}>
            Priority {index + 1}
            <select
              value={value}
              onChange={(e) =>
                change(
                  'priorities',
                  draft.needs.priorities.map((v, i) => (i === index ? e.target.value : v)),
                )
              }
            >
              {criteria.map((key) => (
                <option key={key} value={key}>
                  {label(key)}
                </option>
              ))}
            </select>
          </label>
        ))}
      </fieldset>
      {!unique && (
        <p role="alert" className="error">
          Choose each priority once.
        </p>
      )}
      <fieldset>
        <legend>Coverage requirements</legend>
        {['cancer', 'outpatient', 'mental', 'dental', 'optical'].some(
          (key) => !draft.needs.coverage[key],
        ) && (
          <label>
            Add coverage requirement
            <select
              aria-label="Add coverage requirement"
              value=""
              onChange={(event) => {
                if (event.target.value)
                  change('coverage', {
                    ...draft.needs.coverage,
                    [event.target.value]: { level: 1, importance: 1, must_have: false },
                  });
              }}
            >
              <option value="">Choose a benefit</option>
              {['cancer', 'outpatient', 'mental', 'dental', 'optical']
                .filter((key) => !draft.needs.coverage[key])
                .map((key) => (
                  <option key={key} value={key}>
                    {label(key)}
                  </option>
                ))}
            </select>
          </label>
        )}
        {Object.entries(draft.needs.coverage).map(([key, need]) => (
          <fieldset key={key}>
            <legend>{label(key)}</legend>
            <label>
              Required level
              <select
                value={need.level}
                onChange={(e) => cover(key, 'level', Number(e.target.value))}
              >
                {[0, 1, 2, 3].map((level) => (
                  <option key={level}>{level}</option>
                ))}
              </select>
            </label>
            <label>
              Importance
              <input
                type="number"
                min="0"
                max="1"
                step="0.1"
                value={need.importance}
                onChange={(e) => cover(key, 'importance', Number(e.target.value))}
              />
            </label>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={need.must_have}
                onChange={(e) => cover(key, 'must_have', e.target.checked)}
              />
              Must have
            </label>
          </fieldset>
        ))}
      </fieldset>
      <TextArea
        label="Reason for changes"
        minLength={3}
        required
        value={reason}
        onChange={(e) => setReason(e.target.value)}
      />
      <p role="status">
        {saving ? 'Saving…' : saved === payload ? 'All changes saved' : 'Unsaved changes'}
      </p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="button-row">
        {saved !== payload && (
          <button type="button" className="button small" disabled={saving} onClick={onClose}>
            Discard unsaved changes
          </button>
        )}
        <button className="button primary small" disabled={!valid || saving || saved === payload}>
          Save requirements
        </button>
        <button
          className="button small"
          type="button"
          disabled={saving || saved !== payload}
          onClick={onClose}
        >
          Done
        </button>
      </div>
    </form>
  );
}
