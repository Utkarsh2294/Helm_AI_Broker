import Insights from './Insights';
import OutcomeDetails from './OutcomeDetails';
import React, { useEffect, useState } from 'react';
import { api, label } from '../api';
import BottomSheet from './BottomSheet';
import Reauthenticate from './Reauthenticate';
import TextArea from './TextArea';
export default function Governance({ user }) {
  const [models, setModels] = useState([]),
    [data, setData] = useState({ models: [], events: [] }),
    [edges, setEdges] = useState([]),
    [playbooks, setPlaybooks] = useState([]);
  const [pendingDecision, setPendingDecision] = useState(null);
  const [decisionReason, setDecisionReason] = useState('');
  const [tab, setTab] = useState('models'),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [scope, setScope] = useState(''),
    [guidance, setGuidance] = useState(''),
    [finding, setFinding] = useState({});
  async function load() {
    try {
      const [m, g, e, p] = await Promise.all([
        api('/models'),
        api('/governance'),
        api('/edge-cases'),
        api('/playbooks'),
      ]);
      setModels(m);
      setData(g);
      setEdges(e);
      setPlaybooks(p);
    } catch (e) {
      setError(e.message);
    }
  }
  useEffect(() => {
    load();
  }, []);
  async function change(url, body = {}, method = 'POST', proof = null) {
    setBusy(true);
    setError('');
    try {
      await api(url, { method, body, ...(proof ? { headers: { 'X-Step-Up': proof } } : {}) });
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  const reviewer = user.role === 'compliance_officer' || user.is_lead_broker;
  return (
    <>
      <Insights />
      <OutcomeDetails />
      <div className="learning-summary">
        <div>
          <h2>Learn carefully. Improve deliberately.</h2>
          <p>
            Thirty comparisons, held-out improvement and independent human decisions precede shadow
            mode. A challenger needs thirty new labelled cases and a 0.02 NDCG@3 improvement before
            promotion.
          </p>
        </div>
        {(user.role === 'compliance_officer' || user.role === 'admin' || user.is_lead_broker) && (
          <button className="button" disabled={busy} onClick={() => change('/models/evaluate')}>
            Run evaluation
          </button>
        )}
      </div>
      <div className="table-tabs">
        {['models', 'notebook', 'playbooks', 'decisions'].map((t) => (
          <button key={t} className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>
            {label(t)}
          </button>
        ))}
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {tab === 'models' && (
        <div className="model-list">
          {data.models.map((m) => (
            <article className="surface model-report" key={m.id}>
              <h3>{m.version}</h3>
              <span className="subtle-badge">{label(m.status)}</span>
              <p>
                {m.metrics.distinct_cases} shadow cases · {m.metrics.labelled_cases} labelled
              </p>
              {m.metrics.champion_ndcg3 !== null && (
                <p>
                  NDCG@3: {m.metrics.champion_ndcg3.toFixed(3)} →{' '}
                  {m.metrics.challenger_ndcg3.toFixed(3)}
                </p>
              )}
              {m.status === 'champion' &&
                user.role === 'compliance_officer' &&
                m.version !== 'user-v1' && (
                  <button
                    className="button"
                    disabled={busy}
                    onClick={() => setPendingDecision(`/engine-models/${m.id}/rollback`)}
                  >
                    Roll back champion
                  </button>
                )}
            </article>
          ))}
          {models.map((m) => (
            <article className="surface model-report" key={m.id}>
              <div className="section-header">
                <h3>{label(m.status)}</h3>
                <span>{m.comparison_count} comparisons</span>
              </div>
              {m.champion_metrics && (
                <p>
                  Held-out NDCG@3: {m.champion_metrics.ndcg3.toFixed(3)} →{' '}
                  {m.challenger_metrics.ndcg3.toFixed(3)}
                </p>
              )}
              <div className="weight-bars">
                {Object.entries(m.weights).map(([name, w]) => (
                  <div key={name}>
                    <span>{label(name)}</span>
                    <div className="bar-track">
                      <div style={{ width: `${w * 100}%` }} />
                    </div>
                    <strong>{(w * 100).toFixed(1)}%</strong>
                  </div>
                ))}
              </div>
              {reviewer && m.eligible_for_shadow && (
                <div className="button-row">
                  <button
                    className="button"
                    disabled={busy}
                    onClick={() => setPendingDecision(`/mcr/${m.id}/approve`)}
                  >
                    Approve shadow · G5
                  </button>
                  <button
                    className="button"
                    disabled={busy}
                    onClick={() => setPendingDecision(`/mcr/${m.id}/promote`)}
                  >
                    Approve promotion · G5
                  </button>
                  {['proposed', 'shadow_mode'].includes(m.status) && (
                    <button
                      className="button"
                      disabled={busy}
                      onClick={() => setPendingDecision(`/mcr/${m.id}/reject`)}
                    >
                      Reject model change
                    </button>
                  )}
                </div>
              )}
            </article>
          ))}
          {!models.length && (
            <div className="surface empty-state">
              <h3>Evidence comes first.</h3>
              <p>Case feedback will appear here after an evaluation.</p>
            </div>
          )}
        </div>
      )}
      {tab === 'notebook' && (
        <div className="model-list">
          {edges.map((e) => (
            <article className="surface model-report" key={e.id}>
              <span className="subtle-badge">{label(e.status)}</span>
              <h3>{e.summary}</h3>
              <p>Case {e.case_id.slice(0, 8)}</p>
              <p>{e.survey?.note}</p>
              {e.finding && <p>{e.finding}</p>}
              {reviewer && e.status === 'pending_review' && (
                <>
                  <textarea
                    aria-label={`Finding ${e.id}`}
                    minLength={10}
                    value={finding[e.id] || ''}
                    onChange={(v) => setFinding({ ...finding, [e.id]: v.target.value })}
                  />
                  <button
                    className="button"
                    disabled={busy || (finding[e.id] || '').length < 10}
                    onClick={() =>
                      change(`/edge-cases/${e.id}`, { finding: finding[e.id] }, 'PATCH')
                    }
                  >
                    Record review
                  </button>
                </>
              )}
            </article>
          ))}
          {!edges.length && (
            <div className="surface empty-state">
              <h3>No disputed selections.</h3>
              <p>A thumbs-down creates an entry immediately.</p>
            </div>
          )}
        </div>
      )}
      {tab === 'playbooks' && (
        <section className="surface model-report">
          <h3>Versioned case guidance</h3>
          {playbooks.map((p) => (
            <article className="playbook" key={p.id}>
              <strong>
                {p.scope} · v{p.version}
              </strong>
              <p>{p.guidance}</p>
              <span className="subtle-badge">
                {p.approved_by ? 'Compliance approved' : 'Draft'}
              </span>
              {!p.approved_by && user.role === 'compliance_officer' && (
                <button
                  className="button"
                  disabled={busy}
                  onClick={() => change(`/playbooks/${p.id}/approve`)}
                >
                  Approve guidance
                </button>
              )}
            </article>
          ))}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              change('/playbooks', { scope, guidance });
            }}
          >
            <label>
              Scope
              <input
                required
                minLength={3}
                maxLength={100}
                value={scope}
                onChange={(e) => setScope(e.target.value)}
              />
            </label>
            <label>
              Guidance
              <textarea
                required
                minLength={20}
                maxLength={3000}
                value={guidance}
                onChange={(e) => setGuidance(e.target.value)}
              />
            </label>
            <button className="button" disabled={busy}>
              Create next draft version
            </button>
          </form>
        </section>
      )}
      {tab === 'decisions' && (
        <section className="surface model-report">
          <h3>Governance decisions</h3>
          {data.events.map((e, i) => (
            <p key={`${e.created_at}-${i}`}>
              {label(e.action)} · {new Date(e.created_at).toLocaleString('en-GB')}
            </p>
          ))}
          {!data.events.length && <p>No model approvals recorded.</p>}
        </section>
      )}
      <BottomSheet
        open={Boolean(pendingDecision)}
        onClose={() => setPendingDecision(null)}
        title="Verify model decision"
        description="Confirm your own decision with a fresh, single-use verification. A different authorised reviewer is still required for the second approval."
      >
        {(pendingDecision?.endsWith('/reject') || pendingDecision?.endsWith('/rollback')) && (
          <TextArea
            label="Reason for model decision"
            required
            minLength={20}
            maxLength={2000}
            value={decisionReason}
            onChange={(event) => setDecisionReason(event.target.value)}
          />
        )}
        {(!pendingDecision?.match(/\/(reject|rollback)$/) ||
          decisionReason.trim().length >= 20) && (
          <Reauthenticate
            title="Re-authenticate for G5"
            actionLabel="Verify and record decision"
            onVerified={async (proof) => {
              const url = pendingDecision;
              setPendingDecision(null);
              await change(url, { reason: decisionReason.trim() }, 'POST', proof);
              setDecisionReason('');
            }}
          />
        )}
      </BottomSheet>
    </>
  );
}
