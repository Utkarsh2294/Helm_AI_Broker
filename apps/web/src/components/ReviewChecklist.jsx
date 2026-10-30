import React, { useState } from 'react';
import { api, label } from '../api';
const sections = ['priorities', 'coverage', 'budget', 'household', 'medical_flag'];
export default function ReviewChecklist({ item, onSaved, onError }) {
  const [checked, setChecked] = useState(item.pack.dnr_sections_confirmed || []);
  const [unmet, setUnmet] = useState(item.pack.unmet_needs_addressed || []);
  const [saving, setSaving] = useState(false);
  const [confirmed, setConfirmed] = useState(item.pack.suitability_confirmed_plans || []),
    [overall, setOverall] = useState(Boolean(item.pack.overall_suitability_confirmed));
  const toggle = (values, value) =>
    values.includes(value) ? values.filter((v) => v !== value) : [...values, value];
  async function save() {
    setSaving(true);
    try {
      onSaved(
        await api(`/cases/${item.id}/suitability`, {
          method: 'PUT',
          body: {
            text: item.pack.suitability_final,
            dnr_sections_confirmed: checked,
            unmet_needs_addressed: unmet,
            suitability_confirmed_plans: confirmed,
            overall_suitability_confirmed: overall,
          },
        }),
      );
    } catch (e) {
      onError(e.message);
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="review-checklist">
      <h3>Record your review</h3>
      <p className="muted">
        Confirm each section against the fact-find, then save this review before signing.
      </p>
      {sections.map((section) => (
        <label className="checkbox-label" key={section}>
          <input
            type="checkbox"
            checked={checked.includes(section)}
            onChange={() => setChecked(toggle(checked, section))}
          />
          {label(section)} reviewed
        </label>
      ))}
      {item.pack.unmet_needs.map((n) => {
        const key = `${n.plan_id}:${n.need}`;
        return (
          <label className="checkbox-label" key={key}>
            <input
              type="checkbox"
              checked={unmet.includes(key)}
              onChange={() => setUnmet(toggle(unmet, key))}
            />
            Addressed {label(n.need)} for {n.plan_id}
          </label>
        );
      })}
      {(
        item.pack.suitability_assessments ||
        item.pack.selected.map((plan_id) => ({ plan_id, gaps: [] }))
      ).map((assessment) => (
        <div key={assessment.plan_id}>
          <p>{assessment.explanation_for_consumer}</p>
          {assessment.gaps.map((gap) => (
            <p key={gap} className="notice warning">
              {gap}
            </p>
          ))}
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={confirmed.includes(assessment.plan_id)}
              onChange={() => setConfirmed(toggle(confirmed, assessment.plan_id))}
            />
            I confirm suitability of {assessment.plan_id} against the stated needs and accept
            responsibility for the recorded gaps.
          </label>
        </div>
      ))}
      <label className="checkbox-label">
        <input type="checkbox" checked={overall} onChange={(e) => setOverall(e.target.checked)} />I
        have assessed the demands and needs and confirm the selected plans represent my advice,
        subject to the recorded terms and gaps.
      </label>
      <button
        className="button"
        disabled={
          saving ||
          checked.length !== 5 ||
          unmet.length !== item.pack.unmet_needs.length ||
          confirmed.length !== 3 ||
          !overall
        }
        onClick={save}
      >
        Save review confirmations
      </button>
      {item.pack.suitability_diff?.length > 0 && (
        <details>
          <summary>Changes from the agent draft</summary>
          <pre>{item.pack.suitability_diff.join('\n')}</pre>
        </details>
      )}
      <p className="muted">Cancellation: {item.pack.manifest?.cancellation_notice?.text}</p>
    </div>
  );
}
