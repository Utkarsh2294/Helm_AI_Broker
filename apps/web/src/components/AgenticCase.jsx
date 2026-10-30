import React, { useEffect, useRef, useState } from 'react';
import { ArrowDown, ArrowUp, CheckCheck, ShieldCheck } from 'lucide-react';
import { api, label, money } from '../api';
import { AgentWork, CaseAssistant, DigitalClientFile, useCaseWorkspace } from './CaseIntelligence';

const declaration =
  'I have reviewed the client facts, budget, priorities, coverage, household and medical declaration; the three policies in my chosen order; the suitability statement, every listed gap, terms and disclosures. I confirm suitability and accept responsibility for this fictional recommendation.';

function CoverageGaps({ plan, needs }) {
  const gaps = Object.entries(needs.coverage || {}).filter(
    ([key, need]) => (plan.coverage[key] || 0) < need.level,
  );
  return (
    <div
      className={
        gaps.length || plan.annualPremiumPence > needs.budget_annual_pence
          ? 'notice warning'
          : 'policy-fit'
      }
    >
      {gaps.length ? (
        <ul>
          {gaps.map(([key, need]) => (
            <li key={key}>
              {label(key)}: level {plan.coverage[key] || 0}, below requested {need.level}.
            </li>
          ))}
        </ul>
      ) : (
        <p>Recorded benefit levels meet the requested targets.</p>
      )}
      {plan.annualPremiumPence > needs.budget_annual_pence && (
        <p>Annual premium exceeds the client’s budget.</p>
      )}
      <p>Cover remains subject to underwriting and insurer terms.</p>
    </div>
  );
}

function PolicySelection({ item, busy, onSubmit }) {
  const [selected, setSelected] = useState([]);
  const rows = item.ranking.top,
    needs = item.dnr.needs;
  const names = Object.fromEntries(rows.map((row) => [row.plan.id, row.plan.name]));
  function toggle(id) {
    setSelected((previous) =>
      previous.includes(id)
        ? previous.filter((value) => value !== id)
        : previous.length < 3
          ? [...previous, id]
          : previous,
    );
  }
  function move(index, delta) {
    setSelected((previous) => {
      const next = [...previous];
      [next[index], next[index + delta]] = [next[index + delta], next[index]];
      return next;
    });
  }
  return (
    <section className="human-decision" aria-labelledby="selection-heading">
      <span className="eyebrow">YOUR FIRST DECISION · 1 OF 2</span>
      <h3 id="selection-heading">Choose and rank three policies</h3>
      <p>
        The agents have prepared the comparison. Select three policies below. Selection order
        becomes your preference order; use the arrows to change it.
      </p>
      <div className="selection-summary">
        <strong>{selected.length} of 3 selected</strong>
        <p>
          Annual budget {money(needs.budget_annual_pence)} · priorities:{' '}
          {needs.priorities.map(label).join(' → ')}
        </p>
      </div>
      <div className="automatic-policy-list">
        {rows.map((row) => {
          const plan = row.plan,
            chosen = selected.includes(plan.id);
          return (
            <article className={`automatic-policy ${chosen ? 'chosen' : ''}`} key={plan.id}>
              <div className="automatic-policy-heading">
                <div>
                  <span className="eyebrow">ENGINE RANK {row.rank}</span>
                  <h4>{plan.name}</h4>
                </div>
                <strong>
                  {row.score.toFixed(1)}
                  <small>/100</small>
                </strong>
              </div>
              <p className="policy-price">
                {money(plan.annualPremiumPence)}
                <span>/year, including IPT</span>
              </p>
              <p>{row.explanation.overall}</p>
              <dl className="policy-terms">
                <div>
                  <dt>Excess</dt>
                  <dd>{money(plan.excessPence)}</dd>
                </div>
                <div>
                  <dt>Hospital list</dt>
                  <dd>Level {plan.hospitalListLevel}</dd>
                </div>
                <div>
                  <dt>Underwriting</dt>
                  <dd>{plan.underwritingType}</dd>
                </div>
                <div>
                  <dt>Documents</dt>
                  <dd>
                    {plan.docsRequired - plan.docsUnavailable}/{plan.docsRequired} available
                  </dd>
                </div>
              </dl>
              <CoverageGaps plan={plan} needs={needs} />
              {row.blockers.length > 0 && (
                <p className="notice warning">
                  Outstanding checks: {row.blockers.map(label).join(', ')}
                </p>
              )}
              <details>
                <summary>Why this score and where it came from</summary>
                {Object.entries(row.explanation)
                  .filter(([key]) => key !== 'overall')
                  .map(([key, text]) => (
                    <p key={key}>
                      <strong>{label(key)}: </strong>
                      {text}
                    </p>
                  ))}
                <p>
                  Fit {row.fit.toFixed(1)} · balance {row.balance.toFixed(1)}. Commission is
                  excluded.
                </p>
                <p>
                  IPID: {plan.ipidVersion} · {plan.ipidUrl}
                </p>
                <p>Ranking reference: {item.ranking.id}</p>
              </details>
              <label className="policy-choice">
                <input
                  type="checkbox"
                  checked={chosen}
                  disabled={busy || (!chosen && selected.length === 3)}
                  onChange={() => toggle(plan.id)}
                />
                <span>
                  {chosen
                    ? `Selected · your preference ${selected.indexOf(plan.id) + 1}`
                    : `Select ${plan.name}`}
                </span>
              </label>
            </article>
          );
        })}
      </div>
      <section className="chosen-policy-order" aria-label="Your policy preference order">
        <h4>Your preferred order</h4>
        {!selected.length && <p>Select policies to build your shortlist.</p>}
        <ol>
          {selected.map((id, index) => (
            <li key={id}>
              <span>{names[id]}</span>
              <div>
                <button
                  className="icon-button"
                  aria-label={`Move ${names[id]} up`}
                  disabled={busy || index === 0}
                  onClick={() => move(index, -1)}
                >
                  <ArrowUp size={18} />
                </button>
                <button
                  className="icon-button"
                  aria-label={`Move ${names[id]} down`}
                  disabled={busy || index === selected.length - 1}
                  onClick={() => move(index, 1)}
                >
                  <ArrowDown size={18} />
                </button>
              </div>
            </li>
          ))}
        </ol>
        <p>
          I have reviewed these policies and their displayed gaps and want the agent to prepare a
          recommendation in this order. This does not approve or deliver advice.
        </p>
        <button
          className="button primary"
          disabled={busy || selected.length !== 3}
          onClick={() => onSubmit(selected)}
        >
          {busy ? 'Saving your choices…' : 'Confirm selection & prepare recommendation'}
        </button>
      </section>
    </section>
  );
}

function FinalSignoff({ item, user, busy, onSubmit }) {
  const [password, setPassword] = useState(''),
    [code, setCode] = useState(''),
    [factor, setFactor] = useState(null),
    [factorError, setFactorError] = useState('');
  useEffect(() => {
    let active = true;
    api('/auth/session')
      .then((value) => {
        if (active) setFactor(value.totp_enabled ? 'totp' : 'password');
      })
      .catch((cause) => {
        if (active) setFactorError(cause.message);
      });
    return () => {
      active = false;
    };
  }, []);
  const pack = item.pack,
    needs = item.dnr.needs,
    notice = pack.manifest.cancellation_notice;
  return (
    <section className="human-decision" aria-labelledby="final-signoff-title">
      <span className="eyebrow">YOUR FINAL DECISION · 2 OF 2</span>
      <h3 id="final-signoff-title">Review once. Sign off when ready.</h3>
      <section className="file-section">
        <h4>Client facts and needs</h4>
        <p>
          {item.name} · {label(item.cover_type)} cover · {item.postcode}.
        </p>
        <p>
          Annual budget: {money(needs.budget_annual_pence)}. Priorities:{' '}
          {needs.priorities.map(label).join(' → ')}. Hospital list: level {needs.hospital_level}.
          Underwriting preference: {needs.preferred_underwriting}.
        </p>
        <ul>
          {Object.entries(needs.coverage).map(([key, value]) => (
            <li key={key}>
              {label(key)} · level {value.level}
              {value.must_have ? ' · must have' : ''}
            </li>
          ))}
        </ul>
        <p>
          Sharing consent: {item.dnr.consent_to_share ? 'recorded' : 'not recorded'}. Medical
          statements: {item.dnr.medical_items.length}. No clinical cover conclusion has been made.
        </p>
      </section>
      <h4>Your policy order and recorded gaps</h4>
      <ol className="signed-policy-list">
        {pack.plans.map((row) => (
          <li key={row.plan.id}>
            <h4>{row.plan.name}</h4>
            <p>
              {money(row.plan.annualPremiumPence)}/year including IPT · excess{' '}
              {money(row.plan.excessPence)} · hospital level {row.plan.hospitalListLevel} ·{' '}
              {row.plan.underwritingType}
            </p>
            <CoverageGaps plan={row.plan} needs={needs} />
            <p>
              {
                pack.plan_explanations.find((explanation) => explanation.plan_id === row.plan.id)
                  ?.text
              }
            </p>
            <p>
              IPID reference: {row.plan.ipidVersion}. {row.plan.ipidUrl}
            </p>
          </li>
        ))}
      </ol>
      <section className="file-section">
        <h4>Suitability statement</h4>
        <p>{pack.suitability_final}</p>
      </section>
      <section className="file-section">
        <h4>Terms and disclosures</h4>
        <p>{pack.search_basis}</p>
        <p>{pack.remuneration}</p>
        <p>{pack.manifest.remuneration_panel.fair_value_statement}</p>
        <ul>
          {pack.plans.map((row) => (
            <li key={row.plan.id}>
              {row.plan.name}: {row.plan.commissionPct}% commission. Active fictional terms of
              business: DEMO-TOBA-{row.plan.insurerId}.
            </li>
          ))}
        </ul>
        <p>Cancellation: {notice.text || notice.wording || notice.basis}</p>
        <p>{pack.medical_notice}</p>
      </section>
      <div className="single-signoff">
        <ShieldCheck size={24} />
        <h4>Your decision. Your signature.</h4>
        <p id="final-declaration">{declaration}</p>
        <p>
          Pressing “Sign off & deliver demo” records this declaration against this exact
          recommendation. There is no separate checklist to save.
        </p>
        {factorError && (
          <p className="error" role="alert">
            {factorError}
          </p>
        )}
        {user.can_approve && user.role === 'authorised_broker' ? (
          <form
            aria-describedby="final-declaration"
            onSubmit={(event) => {
              event.preventDefault();
              onSubmit({ password, code });
            }}
          >
            {factor === 'password' && (
              <label>
                Confirm your password
                <input
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  required
                  onChange={(event) => setPassword(event.target.value)}
                />
              </label>
            )}
            {factor === 'totp' && (
              <label>
                Authenticator code
                <input
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  pattern="[0-9]{6}"
                  value={code}
                  required
                  onChange={(event) => setCode(event.target.value)}
                />
              </label>
            )}
            {!factor && !factorError && <p>Checking your verification method…</p>}
            <button className="button primary" disabled={busy || !factor}>
              {busy ? 'Verifying and signing…' : 'Sign off & deliver demo'}
              <ShieldCheck size={17} />
            </button>
          </form>
        ) : (
          <p>An authorised adviser must sign this recommendation.</p>
        )}
        <small>
          Reviewed version: <code>{pack.pack_hash}</code>
        </small>
      </div>
    </section>
  );
}

export default function AgenticCase({ item, user, onSaved, initialView = 'journey' }) {
  const { data, error: loadError } = useCaseWorkspace(item);
  const [view, setView] = useState(initialView),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const decision = useRef(null),
    previousState = useRef(item.state);
  useEffect(() => {
    if (
      item.state !== previousState.current &&
      ['BROKER_REVIEW', 'AWAIT_APPROVAL'].includes(item.state)
    ) {
      decision.current?.scrollIntoView({ block: 'start', behavior: 'smooth' });
      decision.current?.focus({ preventScroll: true });
    }
    previousState.current = item.state;
  }, [item.state]);
  async function submit(path, body) {
    setBusy(true);
    setError('');
    try {
      onSaved(await api(`/demo/journeys/${item.id}/${path}`, { method: 'POST', body }));
    } catch (cause) {
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  }
  async function approve(credentials) {
    setBusy(true);
    setError('');
    try {
      const proof = await api('/auth/step-up', { method: 'POST', body: credentials });
      onSaved(
        await api(`/demo/journeys/${item.id}/signoff`, {
          method: 'POST',
          body: {
            pack_hash: item.pack.pack_hash,
            step_up_token: proof.step_up_token,
            confirm_final_review: true,
          },
        }),
      );
    } catch (cause) {
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  }
  const broker = ['authorised_broker', 'lead_broker'].includes(user.role);
  return (
    <div className="agentic-case">
      <div className="two-decisions">
        <span className="eyebrow">AUTOMATIC FICTIONAL DEMO</span>
        <p>
          <strong>Only two human decisions.</strong> 1. Choose and rank policies. 2. Final sign-off.
          Your agents handle preparation and show their saved work below.
        </p>
      </div>
      <nav className="agentic-navigation" aria-label="Case information">
        <button
          className={`button small ${view === 'journey' ? 'primary' : ''}`}
          aria-current={view === 'journey' ? 'page' : undefined}
          onClick={() => setView('journey')}
        >
          Case journey
        </button>
        <button className="button small" onClick={() => setView('file')}>
          Digital client file
        </button>
        <button className="button small" onClick={() => setView('audit')}>
          Audit trail
        </button>
        <button className="button small" onClick={() => setView('assistant')}>
          Case assistant
        </button>
        <a
          className="button small"
          href={`/api/v1/cases/${item.id}/evidence`}
          download={`helm-case-${item.id}.json`}
        >
          Download evidence
        </a>
      </nav>
      {(error || loadError) && (
        <p role="alert" className="error">
          {error || loadError}
        </p>
      )}
      <div hidden={view !== 'assistant'}>
        <CaseAssistant caseId={item.id} onNavigate={setView} />
      </div>
      {view === 'file' && <DigitalClientFile data={data} />}
      {view === 'audit' && <AgentWork data={data} detailed />}
      {view === 'journey' && (
        <>
          <div className="decision-status" role="status">
            {data?.next_action || 'Agents are preparing your case…'}
          </div>
          <AgentWork data={data} />
          <div ref={decision} tabIndex={-1} className="active-human-decision">
            {item.state === 'BROKER_REVIEW' && broker && (
              <PolicySelection
                key={item.ranking.id}
                item={item}
                busy={busy}
                onSubmit={(selected) =>
                  submit('selection', {
                    ranking_id: item.ranking.id,
                    selected,
                    confirm_selection: true,
                  })
                }
              />
            )}
            {item.state === 'SUITABILITY_DRAFT' && (
              <p className="notice">
                Your choices are saved. Agent 4 is preparing the recommendation automatically.
              </p>
            )}
            {item.state === 'AWAIT_APPROVAL' && item.pack && !item.delivery_pending && (
              <FinalSignoff item={item} user={user} busy={busy} onSubmit={approve} />
            )}
            {item.delivery_pending && (
              <p className="notice">
                Your signed recommendation is queued for delivery. The agent will update this screen
                when acknowledgement is saved.
              </p>
            )}
            {item.state === 'PUBLISHED' && (
              <div className="demo-complete" role="status">
                <CheckCheck size={30} />
                <h3>Signed and delivered.</h3>
                <p>
                  Your recommendation and signature are saved. Agent 5 evaluates your choices
                  automatically and records its result above.
                </p>
              </div>
            )}
            {['PAUSED_NEEDS_HUMAN', 'COMPLAINT_FLAGGED', 'UW_REFERRAL', 'NEEDS_INFO'].includes(
              item.state,
            ) && (
              <p className="notice warning">
                This case has an exception. Automatic work has stopped; no recommendation can be
                approved until the exception is resolved.
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
