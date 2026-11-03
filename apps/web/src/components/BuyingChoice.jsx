import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { api, money } from '../api';

export default function BuyingChoice({ caseId, user }) {
  const [choice, setChoice] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const navigate = useNavigate();
  const query = useQuery({
    queryKey: ['buying-choices', caseId],
    queryFn: () => api(`/policy-buying/choices/${caseId}`),
  });
  if (!['authorised_broker', 'lead_broker', 'senior_broker', 'admin'].includes(user.role))
    return null;
  async function proceed(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api(`/consumer/cases/${caseId}/select-quote`, {
        method: 'POST',
        body: {
          selected_plan_id: choice,
          pack_hash: query.data.pack_hash,
          confirm_selection: true,
        },
      });
      navigate(`/policy-buying/cases/${caseId}`);
    } catch (cause) {
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="surface" aria-label="Demo consumer quote selection">
      <h3>Which plan would the consumer like to proceed with?</h3>
      <p>
        Demo consumer screen. Choose one published plan and explicitly confirm. No real purchase is
        made.
      </p>
      {query.isPending && <p role="status">Loading the signed shortlist…</p>}
      {(error || query.error) && (
        <p className="error" role="alert">
          {error || query.error.message}
        </p>
      )}
      <form onSubmit={proceed}>
        <fieldset>
          <legend>Choose one shortlisted plan</legend>
          {query.data?.plans.map((plan) => (
            <label className="pb-choice" key={plan.id}>
              <input
                type="radio"
                name="consumer-plan"
                value={plan.id}
                checked={choice === plan.id}
                onChange={() => setChoice(plan.id)}
              />
              <span>
                <strong>{plan.name}</strong>
                <small>
                  {plan.insurerId} · {money(plan.annualPremiumPence)} / year ·{' '}
                  {plan.underwritingType}
                </small>
              </span>
            </label>
          ))}
        </fieldset>
        <button className="button primary" disabled={!choice || busy || !query.data} type="submit">
          {busy ? 'Confirming…' : 'Simulate: proceed with this plan'}
        </button>
      </form>
      <Link className="button small" to={`/case/${caseId}?view=journey`}>
        View full recommendation
      </Link>
    </section>
  );
}
