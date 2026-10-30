import React, { useRef, useState } from 'react';
import { api, label } from '../api';

const sections = ['priorities', 'coverage', 'budget', 'household', 'medical_flag'];
const steps = ['Client needs', 'Selected plans', 'Final confirmation'];

export function reviewComplete(pack) {
  return Boolean(
    pack &&
    sections.every((key) => pack.dnr_sections_confirmed?.includes(key)) &&
    pack.selected.every((id) => pack.suitability_confirmed_plans?.includes(id)) &&
    pack.unmet_needs.every((need) =>
      pack.unmet_needs_addressed?.includes(`${need.plan_id}:${need.need}`),
    ) &&
    pack.overall_suitability_confirmed,
  );
}

export default function GuidedReview({
  item,
  onSaved,
  onError,
  onEditing,
  statementDirty = false,
}) {
  const [checked, setChecked] = useState(item.pack.dnr_sections_confirmed || []);
  const [unmet, setUnmet] = useState(item.pack.unmet_needs_addressed || []);
  const [confirmed, setConfirmed] = useState(item.pack.suitability_confirmed_plans || []);
  const [overall, setOverall] = useState(Boolean(item.pack.overall_suitability_confirmed));
  const [step, setStep] = useState(0),
    [saving, setSaving] = useState(false),
    [error, setError] = useState('');
  const [editing, setEditing] = useState(false);
  const area = useRef(null),
    heading = useRef(null);
  const toggle = (values, value) =>
    values.includes(value) ? values.filter((v) => v !== value) : [...values, value];
  const names = Object.fromEntries(item.pack.plans.map((row) => [row.plan.id, row.plan.name]));
  const complete = reviewComplete(item.pack) && !statementDirty;
  const assessments =
    item.pack.suitability_assessments ||
    item.pack.selected.map((plan_id) => ({ plan_id, gaps: [] }));
  const needsReviewed = sections.filter((key) => checked.includes(key)).length;
  const planReviewed = (id) =>
    confirmed.includes(id) &&
    item.pack.unmet_needs
      .filter((n) => n.plan_id === id)
      .every((n) => unmet.includes(`${id}:${n.need}`));
  const plansReviewed = item.pack.selected.filter(planReviewed).length;

  function move(next) {
    setStep(next);
    setError('');
    requestAnimationFrame(() => {
      heading.current?.focus();
      heading.current?.scrollIntoView({ block: 'start' });
    });
  }
  function warn(message) {
    setError(message);
    requestAnimationFrame(() => area.current?.querySelector('input:not(:checked)')?.focus());
  }
  function next() {
    if (step === 0 && needsReviewed !== sections.length)
      return warn(
        `Review the ${sections.length - needsReviewed} remaining client need confirmations before continuing.`,
      );
    if (step === 1 && plansReviewed !== item.pack.selected.length)
      return warn(
        `Review and confirm the ${item.pack.selected.length - plansReviewed} remaining selected plans and their listed gaps.`,
      );
    move(step + 1);
  }
  function confirmPlan(id, value) {
    setConfirmed((old) => (value ? [...new Set([...old, id])] : old.filter((key) => key !== id)));
    const keys = item.pack.unmet_needs
      .filter((n) => n.plan_id === id)
      .map((n) => `${id}:${n.need}`);
    setUnmet((old) =>
      value ? [...new Set([...old, ...keys])] : old.filter((key) => !keys.includes(key)),
    );
  }
  async function save() {
    if (!overall)
      return warn('Confirm that the selected plans represent your advice before saving.');
    if (needsReviewed !== sections.length) return move(0);
    if (plansReviewed !== item.pack.selected.length) return move(1);
    setSaving(true);
    setError('');
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
      setEditing(false);
      requestAnimationFrame(() => document.getElementById('approval-title')?.focus());
    } catch (cause) {
      setError(cause.message);
      onError(cause.message);
    } finally {
      setSaving(false);
    }
  }

  if (complete && !editing)
    return (
      <section className="review-checklist guided-review" aria-label="Saved recommendation review">
        <h3>Review saved. Ready to approve.</h3>
        <p>
          You confirmed the client needs, all three plans and their recorded gaps. Enter your
          password below to approve this version.
        </p>
        <button
          className="text-button"
          onClick={() => {
            setEditing(true);
            onEditing?.();
            move(0);
          }}
        >
          Edit review confirmations
        </button>
      </section>
    );

  return (
    <section
      ref={area}
      className="review-checklist guided-review"
      aria-label="Guided recommendation review"
    >
      <p className="eyebrow">REVIEW BEFORE APPROVAL · STEP {step + 1} OF 3</p>
      <h3 ref={heading} tabIndex={-1}>
        {steps[step]}
      </h3>
      <ol className="review-steps" aria-label="Review progress">
        {steps.map((name, index) => (
          <li key={name} aria-current={index === step ? 'step' : undefined}>
            <span>{index + 1}</span> {name}
          </li>
        ))}
      </ol>
      {statementDirty && (
        <p className="notice warning">
          Your statement has unsaved changes. Click Save statement above before continuing this
          review.
        </p>
      )}
      <fieldset disabled={saving || statementDirty}>
        <legend className="sr-only">{steps[step]}</legend>
        {step === 0 && (
          <>
            <p>
              Check these five areas against the fact-find. {needsReviewed} of {sections.length}{' '}
              confirmed.
            </p>
            {sections.map((section) => (
              <label className="checkbox-label" key={section}>
                <input
                  type="checkbox"
                  checked={checked.includes(section)}
                  onChange={() => setChecked(toggle(checked, section))}
                />
                {section === 'medical_flag' ? 'Medical declaration' : label(section)} reviewed
              </label>
            ))}
          </>
        )}
        {step === 1 && (
          <>
            <p>
              Review each plan and its gaps, then confirm it once. {plansReviewed} of{' '}
              {item.pack.selected.length} confirmed.
            </p>
            {assessments.map((assessment) => {
              const needs = item.pack.unmet_needs.filter((n) => n.plan_id === assessment.plan_id);
              return (
                <div className="review-plan" key={assessment.plan_id}>
                  <h4>{names[assessment.plan_id] || assessment.plan_id}</h4>
                  <p>{assessment.explanation_for_consumer}</p>
                  {(assessment.gaps.length > 0 || needs.length > 0) && (
                    <div className="notice warning">
                      <div>
                        <strong>Gaps to review</strong>
                        <ul>
                          {(assessment.gaps.length
                            ? assessment.gaps
                            : needs.map((n) => label(n.need))
                          ).map((gap, i) => (
                            <li key={i}>{gap}</li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  )}
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={planReviewed(assessment.plan_id)}
                      onChange={(e) => confirmPlan(assessment.plan_id, e.target.checked)}
                    />
                    I reviewed {names[assessment.plan_id] || assessment.plan_id}, confirm its
                    suitability and accept responsibility for the listed gaps.
                  </label>
                </div>
              );
            })}
          </>
        )}
        {step === 2 && (
          <>
            <p>Client needs reviewed · {plansReviewed} plans confirmed · Listed gaps reviewed</p>
            <p>Cancellation: {item.pack.manifest?.cancellation_notice?.text}</p>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={overall}
                onChange={(e) => setOverall(e.target.checked)}
              />
              I have assessed the demands and needs and confirm the selected plans represent my
              advice, subject to the recorded terms and gaps.
            </label>
          </>
        )}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <div className="review-actions">
          {step > 0 && (
            <button className="button" onClick={() => move(step - 1)}>
              Back
            </button>
          )}
          <button className="button primary" onClick={step === 2 ? save : next} disabled={saving}>
            {saving
              ? 'Saving review…'
              : step === 0
                ? 'Continue to selected plans'
                : step === 1
                  ? 'Continue to final confirmation'
                  : 'Save review and continue'}
          </button>
        </div>
      </fieldset>
      {item.pack.suitability_diff?.length > 0 && (
        <details>
          <summary>Changes from the agent draft</summary>
          <pre>{item.pack.suitability_diff.join('\n')}</pre>
        </details>
      )}
    </section>
  );
}
