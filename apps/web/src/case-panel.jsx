import { passkeysAvailable } from './components/PasskeyOrigin';
import SurveySheet from './components/SurveySheet';
import { startAuthentication } from '@simplewebauthn/browser';
import ReplayScrubber from './components/ReplayScrubber';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  X,
  ArrowRight,
  ShieldCheck,
  Check,
  Pause,
  Play,
  Download,
  Clock3,
  FileCheck2,
  AlertTriangle,
  ThumbsUp,
  ThumbsDown,
  ChevronDown,
  LockKeyhole,
  CheckCheck,
  Pencil,
  Save,
} from 'lucide-react';
import { api, label, money } from './api';
import { Status } from './workspace';
import useSSE from './hooks/useSSE';
import AgentPill from './components/AgentPill';
import QuotesBoard from './components/QuotesBoard';
import RankingTools from './components/RankingTools';
import ReviewChecklist, { reviewComplete } from './components/GuidedReview';
import BottomSheet from './components/BottomSheet';
import Reauthenticate from './components/Reauthenticate';
import DnrEditor from './components/DnrEditor';
import MedicalReview from './components/MedicalReview';
import TextArea from './components/TextArea';
import PlanAssessment from './components/PlanAssessment';
import ComplaintHold from './components/ComplaintHold';
import CloseWithoutAdvice from './components/CloseWithoutAdvice';
import ReferralControls from './components/ReferralControls';
import CaseDocuments from './components/CaseDocuments';
import CaseControls from './components/CaseControls';
import AgenticCase from './components/AgenticCase';
import CaseIntelligence from './components/CaseIntelligence';

export default function CasePanel({ id, user, onClose, initialView = 'journey' }) {
  const dialog = useRef(null),
    historicalRef = useRef(false),
    medicalRevealed = useRef(false),
    mutationEpoch = useRef(0);
  const [medicalPrompt, setMedicalPrompt] = useState(false);
  const [complaintPrompt, setComplaintPrompt] = useState(false),
    [complaintReason, setComplaintReason] = useState('');
  const [ratings, setRatings] = useState({}),
    [dirtyRatings, setDirtyRatings] = useState([]);
  const [pausePrompt, setPausePrompt] = useState(false),
    [pauseReason, setPauseReason] = useState('');
  const [historical, setHistorical] = useState(false),
    [liveCase, setLiveCase] = useState(null);
  const [c, setCaseState] = useState(null),
    [tab, setTab] = useState(initialView === 'audit' ? 'activity' : 'overview'),
    [error, setError] = useState('');
  function setCase(value) {
    mutationEpoch.current += 1;
    setCaseState(value);
  }
  const [busy, setBusy] = useState(false),
    [selected, setSelected] = useState([]),
    [thumbs, setThumbs] = useState({});
  const [ack, setAck] = useState([]),
    [note, setNote] = useState(''),
    [omittedReason, setOmittedReason] = useState('');
  const [scenario, setScenario] = useState('happy'),
    [medicalOk, setMedicalOk] = useState(false);
  const [dnrAck, setDnrAck] = useState(false),
    [otp, setOtp] = useState(''),
    [uwRef, setUwRef] = useState('');
  const [password, setPassword] = useState(''),
    [suitability, setSuitability] = useState('');
  const [editing, setEditing] = useState(false);
  const [reviewEditing, setReviewEditing] = useState(false);
  const broker = user.role === 'authorised_broker' && !historical;
  const canRevealMedical =
    !historical && ['authorised_broker', 'compliance_officer'].includes(user.role);
  const canSignOff = !historical && (broker || user.role === 'broker_assistant');
  const liveEvents = useSSE(id, () => refresh());
  const refresh = useCallback(async () => {
    try {
      if (historicalRef.current) return;
      const epoch = mutationEpoch.current;
      const current = await api(
        `/cases/${id}${medicalRevealed.current ? '?include_medical=true' : ''}`,
      );
      if (historicalRef.current || mutationEpoch.current !== epoch) return;
      setCaseState(current);
      setLiveCase(current);
      if (current.demo_workflow) setError('');
    } catch (e) {
      if (e.requires_step_up) medicalRevealed.current = false;
      setError(e.message);
    }
  }, [id]);
  useEffect(() => {
    dialog.current.showModal();
    refresh();
    const timer = setInterval(refresh, 2000);
    return () => clearInterval(timer);
  }, [refresh]);
  useEffect(() => {
    if (c?.pack) setSuitability(c.pack.suitability_final);
  }, [c?.pack?.pack_hash]);
  useEffect(() => {
    if (!c?.ranking?.id) return;
    let active = true;
    setDirtyRatings([]);
    setSelected([]);
    setThumbs({});
    setAck([]);
    api(`/cases/${id}/ratings`)
      .then((result) => {
        if (active) setRatings(Object.fromEntries(result.ratings.map((r) => [r.plan_id, r])));
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [id, c?.ranking?.id]);
  async function action(name, body = {}) {
    setBusy(true);
    setError('');
    try {
      const result = await api(`/cases/${id}/${name}`, { method: 'POST', body });
      setCase(result);
      return result;
    } catch (e) {
      setError(e.message);
      return null;
    } finally {
      setBusy(false);
    }
  }
  async function exportEvidence() {
    setError('');
    try {
      const data = await api(`/cases/${id}/evidence`);
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }),
      );
      const a = document.createElement('a');
      a.href = url;
      a.download = `helm-evidence-${id}.json`;
      a.click();
      URL.revokeObjectURL(url);
      await refresh();
    } catch (e) {
      setError(e.message);
    }
  }
  async function saveSuitability() {
    setBusy(true);
    setError('');
    try {
      setCase(
        await api(`/cases/${id}/suitability`, { method: 'PUT', body: { text: suitability } }),
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function approve() {
    setBusy(true);
    setError('');
    try {
      const proof = await api('/auth/step-up', { method: 'POST', body: { password, code: otp } });
      setCase(
        await api(`/cases/${id}/approve`, {
          method: 'POST',
          body: { pack_hash: c.pack.pack_hash, step_up_token: proof.step_up_token },
        }),
      );
      setPassword('');
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  function togglePlan(planId) {
    if (selected.includes(planId)) {
      setSelected(selected.filter((p) => p !== planId));
      setThumbs(Object.fromEntries(Object.entries(thumbs).filter(([p]) => p !== planId)));
    } else if (selected.length < 3) setSelected([...selected, planId]);
  }
  async function createPack() {
    const result = await action('selection', {
      ranking_id: c.ranking.id,
      selected,
      survey: { thumbs, note, omitted_first_reason: omittedReason },
      acknowledgements: ack,
    });
    if (result) setTab('pack');
  }
  const comparison = c?.ranking?.top || [];
  const reviewedCount = comparison.filter(
    (row) => ratings[row.plan.id] && !dirtyRatings.includes(row.plan.id),
  ).length;
  const allReviewed = comparison.length > 0 && reviewedCount === comparison.length;
  const approvalReady =
    reviewComplete(c?.pack) && !reviewEditing && suitability === c?.pack?.suitability_final;
  const stage = !c
    ? 0
    : ['FACTFIND_REVIEW', 'NEEDS_INFO'].includes(c.state)
      ? 0
      : ['AWAIT_BROKER_RELEASE', 'QUOTES_PENDING'].includes(c.state)
        ? 1
        : c.state === 'BROKER_REVIEW'
          ? 2
          : c.state === 'AWAIT_APPROVAL'
            ? 3
            : c.state === 'PUBLISHED'
              ? 4
              : -1;
  return (
    <dialog
      ref={dialog}
      className="case-panel"
      onCancel={onClose}
      onClick={(e) => {
        if (e.target === dialog.current) onClose();
      }}
      aria-label="Case workspace"
    >
      <div className="panel-inner">
        <AgentPill state={c?.state} events={liveEvents} />
        <header className="panel-header">
          <div>
            <span className="eyebrow">CLIENT WORKSPACE · FICTIONAL DATA</span>
            <h2>{c?.name || 'Opening case…'}</h2>
            {c && (
              <div className="panel-meta">
                <Status state={c.state} />
                <span>
                  {label(c.cover_type)} · {c.postcode}
                </span>
              </div>
            )}
          </div>
          <button className="icon-button" aria-label="Close case" onClick={onClose}>
            <X size={21} />
          </button>
        </header>
        {c && !c.demo_workflow && (
          <>
            <div className="case-stages">
              {['Fact-find', 'Quotations', 'Comparison', 'Approval', 'Delivery'].map((name, i) => (
                <div key={name} className={stage >= i ? 'reached' : ''}>
                  <span>{stage > i ? <Check size={12} /> : i + 1}</span>
                  <small>{name}</small>
                </div>
              ))}
            </div>
            <div className="panel-toolbar">
              <button className="text-button" onClick={exportEvidence}>
                <Download size={14} />
                Evidence
              </button>
              <button
                className="text-button"
                onClick={async () => {
                  try {
                    const r = await fetch(`/api/v1/cases/${id}/evidence`, {
                      headers: { Accept: 'application/pdf' },
                    });
                    if (!r.ok) throw new Error('PDF export failed');
                    const url = URL.createObjectURL(await r.blob());
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `helm-evidence-${id}.pdf`;
                    a.click();
                    URL.revokeObjectURL(url);
                  } catch (e) {
                    setError(e.message);
                  }
                }}
              >
                PDF
              </button>
              {broker && !['PUBLISHED', 'CLOSED', 'COMPLAINT_FLAGGED'].includes(c.state) && (
                <button
                  className="text-button"
                  disabled={busy}
                  onClick={() =>
                    c.state === 'PAUSED_NEEDS_HUMAN' ? action('resume') : setPausePrompt(true)
                  }
                >
                  {c.state === 'PAUSED_NEEDS_HUMAN' ? <Play size={14} /> : <Pause size={14} />}{' '}
                  {c.state === 'PAUSED_NEEDS_HUMAN' ? 'Resume' : 'Pause'}
                </button>
              )}
              {broker && !['CLOSED', 'COMPLAINT_FLAGGED'].includes(c.state) && (
                <button className="text-button" onClick={() => setComplaintPrompt(true)}>
                  Record complaint
                </button>
              )}
            </div>
            {broker && c.state !== 'CLOSED' && (
              <CaseControls item={c} user={user} container={dialog.current} onSaved={refresh} />
            )}
            <div className="panel-tabs" role="tablist" aria-label="Case views">
              {[
                ['overview', 'Fact-find'],
                ['quotes', `Compare${comparison.length ? ` (${comparison.length})` : ''}`],
                ['pack', 'Recommendation'],
                ['activity', 'Audit trail'],
                ['file', 'Digital client file'],
                ['assistant', 'Case assistant'],
              ].map(([key, name]) => (
                <button
                  role="tab"
                  aria-selected={tab === key}
                  aria-controls={`panel-${key}`}
                  id={`tab-${key}`}
                  key={key}
                  className={tab === key ? 'active' : ''}
                  onClick={() => setTab(key)}
                >
                  {name}
                </button>
              ))}
            </div>
          </>
        )}
        <div className="panel-body">
          {c?.demo_workflow && (
            <AgenticCase item={c} user={user} onSaved={setCase} initialView={initialView} />
          )}
          {liveCase && !c?.demo_workflow && (
            <ReplayScrubber
              item={liveCase}
              onView={(v) => {
                historicalRef.current = true;
                setHistorical(true);
                setCase(v);
              }}
              onPresent={() => {
                historicalRef.current = false;
                setHistorical(false);
                refresh();
              }}
            />
          )}{' '}
          {historical && !c?.dnr && (
            <p className="notice">The fact-find had not been recorded at this time.</p>
          )}
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          {!c && <p className="muted">Loading case details…</p>}
          {c?.dnr && !c.demo_workflow && (
            <section role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
              {c.state === 'PAUSED_NEEDS_HUMAN' && (
                <div className="notice warning">
                  <AlertTriangle size={18} />
                  <div>
                    <strong>Your expertise is needed.</strong>
                    <p>
                      {label(
                        c.events.filter((e) => e.payload.reason).at(-1)?.payload.reason ||
                          'Review this case before resuming.',
                      )}
                    </p>
                    {c.quotes?.partners.some((p) =>
                      ['clarification', 'referred'].includes(p.state),
                    ) &&
                      broker && (
                        <button
                          className="button small"
                          disabled={busy}
                          onClick={() => action('resolve')}
                        >
                          Resolve fictional partner exception
                        </button>
                      )}
                  </div>
                </div>
              )}
              {broker && c.medical_triage && !c.medical_review?.resolved && (
                <MedicalReview
                  item={c}
                  revealed={medicalRevealed.current}
                  onSaved={(value) => {
                    setCase(value);
                    refresh();
                  }}
                />
              )}
              {broker && !dirtyRatings.length && (
                <ReferralControls
                  item={c}
                  ratings={ratings}
                  container={dialog.current}
                  onSaved={refresh}
                />
              )}
              {c.state === 'UW_REFERRAL' && !c.broker_referral && (
                <div className="notice warning">
                  <div>
                    <h3>Underwriter confirmation required · G3</h3>
                    <label>
                      Fictional underwriter reference
                      <input value={uwRef} onChange={(e) => setUwRef(e.target.value)} />
                    </label>
                    {broker && (
                      <button
                        className="button"
                        disabled={busy || uwRef.length < 3}
                        onClick={() => action('resolve', { underwriter_reference: uwRef })}
                      >
                        Record confirmation and recollect
                      </button>
                    )}
                  </div>
                </div>
              )}
              {c.state === 'COMPLAINT_FLAGGED' && (
                <ComplaintHold item={c} user={user} onResolved={refresh} />
              )}
              {tab === 'overview' && (
                <>
                  {c.consumer_response && (
                    <p className="notice" role="status">
                      Consumer response: {label(c.consumer_response.decision)}.{' '}
                      {c.policy_bound
                        ? 'Fictional binding confirmation recorded.'
                        : c.state === 'CLOSED'
                          ? 'Case closed.'
                          : 'Review the consumer response before taking the next step.'}
                    </p>
                  )}
                  {c.consumer_link?.type === 'consumer.magic_link_expired' && (
                    <p className="notice warning" role="status">
                      The consumer link expired. Review the case before arranging a fresh handoff.
                    </p>
                  )}
                  {c.state === 'CLOSED' && (
                    <a className="button small" href={`/api/v1/cases/${id}/closure.pdf`} download>
                      Download closure record
                    </a>
                  )}
                  <div className="section-header">
                    <h3>Demands & needs record</h3>
                    <span className="subtle-badge">VERSION {c.dnr.version}</span>
                  </div>
                  <p className="muted">
                    Review the consumer's requirements before the quotation request is released.
                  </p>
                  <dl className="facts-grid">
                    <div>
                      <dt>Annual budget</dt>
                      <dd>{money(c.dnr.needs.budget_annual_pence)}</dd>
                    </div>
                    <div>
                      <dt>Cover type</dt>
                      <dd>{label(c.cover_type)}</dd>
                    </div>
                    <div>
                      <dt>Hospital network</dt>
                      <dd>Level {c.dnr.needs.hospital_level}</dd>
                    </div>
                    <div>
                      <dt>Underwriting preference</dt>
                      <dd>{label(c.dnr.needs.preferred_underwriting)}</dd>
                    </div>
                  </dl>
                  {canRevealMedical && (
                    <CaseDocuments
                      item={c}
                      revealed={medicalRevealed.current}
                      onReveal={() => setMedicalPrompt(true)}
                      editable={broker && ['FACTFIND_REVIEW', 'NEEDS_INFO'].includes(c.state)}
                    />
                  )}
                  <h4 className="field-caption">PRIORITIES, IN ORDER</h4>
                  <div className="priority-chips">
                    {c.dnr.needs.priorities.map((p, i) => (
                      <span key={p}>
                        <b>{i + 1}</b>
                        {label(p)}
                      </span>
                    ))}
                  </div>
                  <h4 className="field-caption">COVERAGE REQUIREMENTS</h4>
                  <div className="coverage-list">
                    {Object.entries(c.dnr.needs.coverage).map(([key, value]) => (
                      <div key={key}>
                        <span>{label(key)}</span>
                        <strong>Level {value.level}</strong>
                        {value.must_have && <span className="subtle-badge">MUST HAVE</span>}
                      </div>
                    ))}
                  </div>
                  {c.dnr.missing.length > 0 && (
                    <p className="notice warning">Missing: {c.dnr.missing.join(', ')}</p>
                  )}
                  <div className="notice">
                    <ShieldCheck size={19} />
                    <div>
                      <strong>
                        {c.dnr.consent_to_share
                          ? 'Consent to share is recorded'
                          : 'Consent is missing'}
                      </strong>
                      <p>
                        Medical statements are preserved verbatim. No diagnosis or coverage
                        consequence is inferred.
                      </p>
                    </div>
                  </div>
                  {canRevealMedical && c.dnr.medical_items.includes('[REDACTED]') && (
                    <button className="text-button" onClick={() => setMedicalPrompt(true)}>
                      Reveal medical statements
                    </button>
                  )}
                  {medicalRevealed.current && (
                    <button
                      className="text-button"
                      onClick={() => {
                        medicalRevealed.current = false;
                        refresh();
                      }}
                    >
                      Hide medical statements
                    </button>
                  )}
                  {c.dnr.medical_items.map((text, i) => (
                    <blockquote className="medical-verbatim" key={i}>
                      {text}
                    </blockquote>
                  ))}
                  <details className="source-details">
                    <summary>
                      Facts & provenance
                      <ChevronDown size={15} />
                    </summary>
                    {Object.entries(c.dnr.facts).map(([key, fact]) => (
                      <div key={key}>
                        <strong>{label(key)}</strong>
                        <span>{Math.round(fact.confidence * 100)}% confidence</span>
                        <code>{fact.source}</code>
                      </div>
                    ))}
                  </details>
                  <details className="source-details">
                    <summary>
                      Needs research · hypotheses
                      <ChevronDown size={15} />
                    </summary>
                    {c.dnr.hypotheses.map((h) => (
                      <p key={h} className="muted">
                        {h}
                      </p>
                    ))}
                  </details>
                  {broker &&
                    ['FACTFIND_REVIEW', 'AWAIT_BROKER_RELEASE', 'NEEDS_INFO'].includes(c.state) && (
                      <div className="requirements-edit">
                        {!editing ? (
                          <button
                            className="text-button"
                            onClick={() => {
                              setEditing(true);
                            }}
                          >
                            <Pencil size={14} />
                            Edit stated requirements
                          </button>
                        ) : (
                          <DnrEditor
                            item={c}
                            onSaved={(value) => {
                              setCase(value);
                              setDnrAck(false);
                            }}
                            onClose={() => setEditing(false)}
                          />
                        )}
                      </div>
                    )}
                  {canSignOff && c.state === 'FACTFIND_REVIEW' && (
                    <div className="action-area">
                      <label className="checkbox-label">
                        <input
                          type="checkbox"
                          checked={dnrAck}
                          onChange={(e) => setDnrAck(e.target.checked)}
                        />
                        I reviewed this fact-find and its vulnerability indicators.
                      </label>
                      <button
                        className="button primary"
                        disabled={busy || editing || !dnrAck || c.dnr.missing.length > 0}
                        onClick={() =>
                          action('sign-off', {
                            dnr_acknowledged: dnrAck,
                            vulnerability_acknowledged: dnrAck,
                          })
                        }
                      >
                        Sign off fact-find
                        <ArrowRight size={16} />
                      </button>
                    </div>
                  )}
                  {broker && c.state === 'AWAIT_BROKER_RELEASE' && (
                    <div className="action-area">
                      <h3>Ready to explore the panel.</h3>
                      <p>Send a minimised RFQ to all five eligible demo partners.</p>
                      <label>
                        Demo scenario
                        <select value={scenario} onChange={(e) => setScenario(e.target.value)}>
                          {[
                            ['happy', 'All partners quote'],
                            ['decline', 'One partner declines'],
                            ['late', 'One late response'],
                            ['arithmetic', 'Premium arithmetic mismatch'],
                            ['medical', 'Medical clarification'],
                            ['duplicate', 'Duplicate response'],
                            ['referral', 'Underwriter referral'],
                            ['injection', 'Untrusted partner instructions'],
                          ].map(([key, title]) => (
                            <option key={key} value={key}>
                              {title}
                            </option>
                          ))}
                        </select>
                      </label>
                      {c.dnr.medical_items.length > 0 && (
                        <label className="checkbox-label">
                          <input
                            type="checkbox"
                            checked={medicalOk}
                            onChange={(e) => setMedicalOk(e.target.checked)}
                          />
                          I authorise sharing the medical category flag with the fictional partners.
                        </label>
                      )}
                      <button
                        className="button primary"
                        disabled={busy || editing || (c.dnr.medical_items.length > 0 && !medicalOk)}
                        onClick={() => action('release', { scenario, medical_released: medicalOk })}
                      >
                        Release demo RFQ
                        <ArrowRight size={16} />
                      </button>
                    </div>
                  )}
                  {c.state === 'QUOTES_PENDING' && (
                    <div className="waiting-block">
                      <Clock3 size={27} />
                      <h3>Your quotation agent is on it.</h3>
                      <p>
                        The six-hour business window is compressed to about six seconds by the
                        default demo clock.
                      </p>
                      <span className="state-badge amber">
                        <span />
                        Collecting partner quotations
                      </span>
                    </div>
                  )}
                  {c.state === 'BROKER_REVIEW' && (
                    <div className="action-area">
                      <h3>Your comparison is ready.</h3>
                      <p>Review scores, terms, uncertainty and outstanding blockers.</p>
                      <button className="button primary" onClick={() => setTab('quotes')}>
                        Compare top five
                        <ArrowRight size={16} />
                      </button>
                    </div>
                  )}
                </>
              )}
              {tab === 'quotes' && (
                <>
                  {c.rfq && <QuotesBoard item={c} />} {c.ranking && <RankingTools item={c} />}{' '}
                  {!c.ranking ? (
                    <div className="empty-state">
                      <Clock3 size={30} />
                      <h2>Good comparisons take good inputs.</h2>
                      <p>Sign off the fact-find and release a quotation request first.</p>
                    </div>
                  ) : (
                    <>
                      <div className="section-header">
                        <h3>The top five, explained.</h3>
                        <span className="subtle-badge">{c.ranking.engine_version}</span>
                      </div>
                      <p className="muted">
                        Review each plan and choose three as you go. Scores are commission-blind.
                      </p>
                      {c.ranking.joint_first && (
                        <div className="notice">
                          <ChartNotice />
                          <div>
                            <strong>The leading plans are effectively tied.</strong>
                            <p>
                              Small changes in priorities can change their order. Review the
                              trade-offs.
                            </p>
                          </div>
                        </div>
                      )}
                      <div className="quote-list">
                        {broker && c.state === 'BROKER_REVIEW' && (
                          <div className="comparison-guide">
                            <p role="status">
                              Rated {reviewedCount} of {comparison.length} plans. Selected{' '}
                              {selected.length} of 3.
                            </p>
                            <p className="muted">
                              Save each assessment to select that plan. Review all five before
                              preparing the recommendation.
                            </p>
                            {!allReviewed && (
                              <button
                                className="button small"
                                onClick={() => {
                                  const next = comparison.find(
                                    (row) =>
                                      !ratings[row.plan.id] || dirtyRatings.includes(row.plan.id),
                                  );
                                  const element = document.getElementById(`plan-${next.plan.id}`);
                                  element?.focus();
                                  element?.scrollIntoView({ block: 'start' });
                                }}
                              >
                                Review next unfinished plan
                              </button>
                            )}
                            {allReviewed && selected.length === 3 && (
                              <button
                                className="button primary small"
                                onClick={() =>
                                  document.getElementById('selection-feedback')?.click()
                                }
                              >
                                Continue to recommendation
                              </button>
                            )}
                          </div>
                        )}
                        {comparison.map((row, i) => {
                          const plan = row.plan,
                            isSelected = selected.includes(plan.id);
                          const selectionBlocker = busy
                            ? 'Please wait for the current action to finish.'
                            : dirtyRatings.includes(plan.id)
                              ? 'Save your changes to this assessment before selecting plans.'
                              : !ratings[plan.id]
                                ? 'Save a star rating, decision and reason for this plan first. You can then select it while reviewing the other plans.'
                                : ratings[plan.id].decision !== 'YES'
                                  ? 'Only plans assessed as Recommend can be selected. Change and save your assessment if appropriate.'
                                  : !isSelected && selected.length >= 3
                                    ? 'Three plans are already selected. Deselect one to choose a different plan.'
                                    : null;
                          return (
                            <article
                              className={`quote-card ${isSelected ? 'selected' : ''}`}
                              key={plan.id}
                              id={`plan-${plan.id}`}
                              tabIndex={-1}
                            >
                              <div className="quote-top">
                                <span className="rank-label">
                                  {c.ranking.joint_first && i < 2 ? 'JOINT #1' : `#${i + 1}`}
                                </span>
                                <strong className="quote-score">
                                  {row.score.toFixed(1)}
                                  <small>/100</small>
                                </strong>
                              </div>
                              <h3>{plan.name}</h3>
                              <div className="quote-price">
                                {money(plan.annualPremiumPence)}
                                <small> / year, including IPT</small>
                              </div>
                              <p className="muted quote-description">
                                {typeof row.explanation === 'string'
                                  ? row.explanation
                                  : row.explanation?.overall}
                              </p>
                              <div className="quote-keyfacts">
                                <span>
                                  Excess <b>{money(plan.excessPence)}</b>
                                </span>
                                <span>
                                  Hospital list <b>Level {plan.hospitalListLevel}</b>
                                </span>
                                <span>
                                  Documents{' '}
                                  <b>
                                    {plan.docsRequired - plan.docsUnavailable}/{plan.docsRequired}{' '}
                                    available
                                  </b>
                                </span>
                              </div>
                              {row.blockers.length > 0 && (
                                <div className="blocker-chips">
                                  {row.blockers.map((b) => (
                                    <span key={b}>
                                      <AlertTriangle size={11} />
                                      {label(b)}
                                    </span>
                                  ))}
                                </div>
                              )}
                              <details className="score-details">
                                <summary>
                                  Score, stability & source
                                  <ChevronDown size={14} />
                                </summary>
                                <div className="weight-bars">
                                  {Object.entries(row.points).map(([name, points]) => (
                                    <div key={name}>
                                      <span>{label(name)}</span>
                                      <div className="bar-track">
                                        <div
                                          style={{
                                            width: `${(points / Math.max(...Object.values(row.points))) * 100}%`,
                                          }}
                                        />
                                      </div>
                                      <strong>{points.toFixed(1)}</strong>
                                    </div>
                                  ))}
                                </div>
                                <p className="muted">
                                  Additive fit {row.fit.toFixed(1)} · Balance{' '}
                                  {row.balance.toFixed(1)}
                                  <br />
                                  First in {(row.stability.pTop1 * 100).toFixed(1)}% of{' '}
                                  {c.ranking.draws} weightings.
                                  <br />
                                  95% score interval:{' '}
                                  {row.stability.scoreInterval.map((v) => v.toFixed(1)).join('–')}
                                </p>
                                <p className="muted">
                                  Commission: {plan.commissionPct}% · Excluded from ranking
                                </p>
                                <code>{plan.provenance.basePremiumPence}</code>
                                <p className="muted">
                                  IPID reference: {plan.ipidVersion} · Synthetic document
                                </p>
                              </details>
                              {typeof row.explanation === 'object' && (
                                <details className="score-details">
                                  <summary>Why these scores</summary>
                                  {Object.entries(row.explanation)
                                    .filter(([key]) => key !== 'overall')
                                    .map(([key, text]) => (
                                      <div key={key} className="criterion-explanation">
                                        <strong>
                                          {label(key)} · {(c.ranking.weights[key] * 100).toFixed(1)}
                                          %
                                        </strong>
                                        <progress
                                          aria-label={`${label(key)} utility for ${plan.name}`}
                                          max="1"
                                          value={row.utilities[key]}
                                        />
                                        <p>{text}</p>
                                      </div>
                                    ))}
                                </details>
                              )}
                              {broker && c.state === 'BROKER_REVIEW' && (
                                <>
                                  <PlanAssessment
                                    key={`${c.ranking.id}:${plan.id}:${ratings[plan.id]?.id || 'draft'}`}
                                    caseId={id}
                                    rankingId={c.ranking.id}
                                    row={row}
                                    rating={ratings[plan.id]}
                                    onDirty={(planId) => {
                                      setDirtyRatings((old) =>
                                        old.includes(planId) ? old : [...old, planId],
                                      );
                                      setSelected((old) => old.filter((id) => id !== planId));
                                      setThumbs((old) =>
                                        Object.fromEntries(
                                          Object.entries(old).filter(([id]) => id !== planId),
                                        ),
                                      );
                                      setAck((old) => old.filter((id) => id !== planId));
                                    }}
                                    onSaved={(rating) => {
                                      setRatings((old) => ({ ...old, [plan.id]: rating }));
                                      setDirtyRatings((old) =>
                                        old.filter((key) => key !== plan.id),
                                      );
                                    }}
                                  />
                                  <button
                                    className={`button full ${isSelected ? 'primary' : ''}`}
                                    disabled={Boolean(selectionBlocker)}
                                    aria-describedby={
                                      selectionBlocker ? `selection-help-${i}` : undefined
                                    }
                                    onClick={() => togglePlan(plan.id)}
                                  >
                                    {isSelected ? (
                                      <>
                                        <Check size={15} />
                                        Selected · preference {selected.indexOf(plan.id) + 1}
                                      </>
                                    ) : (
                                      'Select this plan'
                                    )}
                                  </button>
                                  {selectionBlocker && (
                                    <p id={`selection-help-${i}`} className="muted">
                                      {selectionBlocker}
                                    </p>
                                  )}
                                  {isSelected && row.blockers.length > 0 && (
                                    <label className="checkbox-label">
                                      <input
                                        type="checkbox"
                                        checked={ack.includes(plan.id)}
                                        onChange={(e) =>
                                          setAck(
                                            e.target.checked
                                              ? [...ack, plan.id]
                                              : ack.filter((p) => p !== plan.id),
                                          )
                                        }
                                      />
                                      I reviewed and acknowledge these blockers.
                                    </label>
                                  )}
                                </>
                              )}
                            </article>
                          );
                        })}
                      </div>
                      {c.ranking.flip && (
                        <p className="muted">
                          A {(c.ranking.flip.amount * 100).toFixed(0)}-point weight shift from{' '}
                          {label(c.ranking.flip.from).toLowerCase()} to{' '}
                          {label(c.ranking.flip.to).toLowerCase()} changes the leading order.
                        </p>
                      )}
                      {(c.ranking.excluded.length > 0 || c.ranking.needs_human.length > 0) && (
                        <details className="source-details">
                          <summary>
                            Excluded & referred quotations
                            <ChevronDown size={15} />
                          </summary>
                          {[...c.ranking.excluded, ...c.ranking.needs_human].map((row) => (
                            <p key={row.plan.id}>
                              {row.plan.name}: {row.reasons.map(label).join(', ')}
                            </p>
                          ))}
                        </details>
                      )}
                      {c.quotes && (
                        <details className="source-details">
                          <summary>
                            All partner responses
                            <ChevronDown size={15} />
                          </summary>
                          {c.quotes.partners.map((p) => (
                            <p key={p.id}>
                              {p.name}: {label(p.state)}
                              {p.injection_blocked ? ' · Untrusted instructions ignored' : ''}
                            </p>
                          ))}
                        </details>
                      )}
                      {broker && c.state === 'BROKER_REVIEW' && allReviewed && (
                        <CloseWithoutAdvice
                          item={c}
                          ratings={ratings}
                          container={dialog.current}
                          onClosed={refresh}
                        />
                      )}
                      {broker &&
                        c.state === 'BROKER_REVIEW' &&
                        allReviewed &&
                        selected.length > 0 && (
                          <SurveySheet
                            container={dialog.current}
                            ready={selected.length === 3}
                            id="selection-feedback"
                          >
                            <div className="feedback-area">
                              <h3>Order your three selected plans</h3>
                              {selected.map((planId, index) => (
                                <div
                                  className="button-row"
                                  key={planId}
                                  draggable
                                  onDragStart={(event) =>
                                    event.dataTransfer.setData('text/plain', planId)
                                  }
                                  onDragOver={(event) => event.preventDefault()}
                                  onDrop={(event) => {
                                    event.preventDefault();
                                    const moved = event.dataTransfer.getData('text/plain');
                                    if (!selected.includes(moved) || moved === planId) return;
                                    const order = selected.filter((id) => id !== moved);
                                    order.splice(order.indexOf(planId), 0, moved);
                                    setSelected(order);
                                  }}
                                >
                                  <span>
                                    {index + 1}.{' '}
                                    {comparison.find((row) => row.plan.id === planId)?.plan.name}
                                  </span>
                                  <button
                                    className="button small"
                                    aria-label={`Move ${planId} up`}
                                    disabled={index === 0}
                                    onClick={() => {
                                      const order = [...selected];
                                      [order[index - 1], order[index]] = [
                                        order[index],
                                        order[index - 1],
                                      ];
                                      setSelected(order);
                                    }}
                                  >
                                    ↑
                                  </button>
                                  <button
                                    className="button small"
                                    aria-label={`Move ${planId} down`}
                                    disabled={index === selected.length - 1}
                                    onClick={() => {
                                      const order = [...selected];
                                      [order[index + 1], order[index]] = [
                                        order[index],
                                        order[index + 1],
                                      ];
                                      setSelected(order);
                                    }}
                                  >
                                    ↓
                                  </button>
                                </div>
                              ))}
                              <span className="eyebrow">A QUICK SENSE CHECK</span>
                              <h3>Did the scores and explanations look right?</h3>
                              {selected.map((planId) => (
                                <div className="thumb-row" key={planId}>
                                  <span>
                                    {comparison.find((r) => r.plan.id === planId).plan.name}
                                  </span>
                                  <button
                                    aria-label={`Score looks right for ${planId}`}
                                    aria-pressed={thumbs[planId] === 'up'}
                                    onClick={() => setThumbs({ ...thumbs, [planId]: 'up' })}
                                  >
                                    <ThumbsUp size={16} />
                                  </button>
                                  <button
                                    aria-label={`Dispute score for ${planId}`}
                                    aria-pressed={thumbs[planId] === 'down'}
                                    onClick={() => setThumbs({ ...thumbs, [planId]: 'down' })}
                                  >
                                    <ThumbsDown size={16} />
                                  </button>
                                </div>
                              ))}
                              {!selected.includes(comparison[0]?.plan.id) && (
                                <label>
                                  Why wasn't the engine's first plan selected?
                                  <input
                                    maxLength={140}
                                    required
                                    value={omittedReason}
                                    onChange={(e) => setOmittedReason(e.target.value)}
                                  />
                                </label>
                              )}
                              <label>
                                Anything else? <small>Optional · 140 characters</small>
                                <textarea
                                  maxLength={140}
                                  value={note}
                                  onChange={(e) => setNote(e.target.value)}
                                  placeholder="A short note for the learning agent…"
                                />
                              </label>
                              <button
                                className="button primary full"
                                disabled={
                                  busy || selected.length !== 3 || selected.some((p) => !thumbs[p])
                                }
                                onClick={createPack}
                              >
                                Prepare recommendation pack
                                <ArrowRight size={16} />
                              </button>
                            </div>
                          </SurveySheet>
                        )}
                    </>
                  )}
                </>
              )}
              {tab === 'pack' && (
                <>
                  {!c.pack ? (
                    <div className="empty-state">
                      <FileCheck2 size={30} />
                      <h2>Bring your recommendation together.</h2>
                      <p>Select three plans and give brief feedback to prepare the pack.</p>
                      <button className="button" onClick={() => setTab('quotes')}>
                        View comparison
                        <ArrowRight size={16} />
                      </button>
                    </div>
                  ) : (
                    <>
                      <div className="section-header">
                        <h3>Your recommendation pack</h3>
                        <span className="subtle-badge">DEMO PREVIEW</span>
                      </div>
                      <div className="pack-plans">
                        {c.pack.plans.map((r, i) => (
                          <div key={r.plan.id}>
                            <span>{i + 1}</span>
                            <strong>{r.plan.name}</strong>
                            <b>{money(r.plan.annualPremiumPence)}</b>
                          </div>
                        ))}
                      </div>
                      <label className="suitability-label">
                        Suitability statement
                        <textarea
                          rows={9}
                          value={suitability}
                          disabled={c.state !== 'AWAIT_APPROVAL' || !broker}
                          onChange={(e) => setSuitability(e.target.value)}
                        />
                      </label>
                      {broker &&
                        c.state === 'AWAIT_APPROVAL' &&
                        suitability !== c.pack.suitability_final && (
                          <button
                            className="button small"
                            disabled={busy}
                            onClick={saveSuitability}
                          >
                            <Save size={14} />
                            Save statement
                          </button>
                        )}
                      <div className="pack-disclosures">
                        <p>
                          <strong>Search basis</strong>
                          {c.pack.search_basis}
                        </p>
                        <p>
                          <strong>Remuneration</strong>
                          {c.pack.remuneration}
                        </p>
                        <p>
                          <strong>Medical terms</strong>
                          {c.pack.medical_notice}
                        </p>
                        <p>
                          <strong>Unmet needs</strong>
                          {c.pack.unmet_needs.length
                            ? c.pack.unmet_needs.map((n) => label(n.need)).join(', ')
                            : 'None against the recorded coverage-level targets.'}
                        </p>
                        <p>
                          <strong>Rule pack</strong>
                          {c.pack.rule_pack_version}
                        </p>
                      </div>
                      {broker && c.state === 'AWAIT_APPROVAL' && (
                        <ReviewChecklist
                          key={c.pack.pack_hash}
                          item={c}
                          onSaved={(value) => {
                            setReviewEditing(false);
                            setCase(value);
                          }}
                          onError={setError}
                          onEditing={() => setReviewEditing(true)}
                          statementDirty={suitability !== c.pack.suitability_final}
                        />
                      )}{' '}
                      {broker &&
                        c.state === 'AWAIT_APPROVAL' &&
                        !c.delivery_pending &&
                        approvalReady && (
                          <div className="approval-area">
                            <LockKeyhole size={24} />
                            <h3 id="approval-title" tabIndex={-1}>
                              Final step: approve recommendation
                            </h3>
                            <p>
                              Your review is saved. Enter your password to approve this
                              recommendation. Use your authenticator code too if you enabled one.
                            </p>
                            {passkeysAvailable() && (
                              <details>
                                <summary>Use a passkey instead</summary>
                                <button
                                  className="button full"
                                  disabled={
                                    busy ||
                                    !passkeysAvailable() ||
                                    c.pack.dnr_sections_confirmed?.length !== 5
                                  }
                                  onClick={async () => {
                                    setBusy(true);
                                    setError('');
                                    try {
                                      const o = await api('/auth/passkey/options', {
                                        method: 'POST',
                                        body: { step_up: true },
                                      });
                                      const credential = await startAuthentication({
                                        optionsJSON: o.options,
                                      });
                                      const proof = await api('/auth/passkey/verify', {
                                        method: 'POST',
                                        body: { challenge_id: o.challenge_id, credential },
                                      });
                                      setCase(
                                        await api(`/cases/${id}/approve`, {
                                          method: 'POST',
                                          body: {
                                            pack_hash: c.pack.pack_hash,
                                            step_up_token: proof.step_up_token,
                                          },
                                        }),
                                      );
                                    } catch (e) {
                                      setError(e.message);
                                    } finally {
                                      setBusy(false);
                                    }
                                  }}
                                >
                                  Approve with passkey
                                </button>
                              </details>
                            )}
                            <form
                              onSubmit={(e) => {
                                e.preventDefault();
                                approve();
                              }}
                            >
                              <label>
                                Confirm your password
                                <input
                                  type="password"
                                  required
                                  autoComplete="current-password"
                                  value={password}
                                  onChange={(e) => setPassword(e.target.value)}
                                />
                              </label>
                              <label>
                                Authenticator code (if enrolled)
                                <input
                                  autoComplete="one-time-code"
                                  inputMode="numeric"
                                  value={otp}
                                  onChange={(e) => setOtp(e.target.value)}
                                />
                              </label>
                              <button
                                className="button primary full"
                                disabled={
                                  busy ||
                                  suitability !== c.pack.suitability_final ||
                                  c.pack.dnr_sections_confirmed?.length !== 5
                                }
                              >
                                Approve demo recommendation
                                <ShieldCheck size={16} />
                              </button>
                            </form>
                            <button
                              className="text-button"
                              disabled={busy}
                              onClick={() => action('request-changes')}
                            >
                              Return to comparison
                            </button>
                          </div>
                        )}
                      {c.delivery_pending && (
                        <div className="notice">
                          <div>
                            <h3>Approval recorded. Awaiting Core acknowledgement.</h3>
                            <p>
                              The delivery job is persisted. This case becomes Published after the
                              acknowledgement arrives.
                            </p>
                          </div>
                        </div>
                      )}
                      {c.state === 'PUBLISHED' && (
                        <div className="delivery-success">
                          <CheckCheck size={29} />
                          <h2>Approved. Ready for the next step.</h2>
                          <p>
                            The exact pack and human approval are recorded. Consumer delivery was
                            simulated.
                          </p>
                        </div>
                      )}
                    </>
                  )}
                </>
              )}
              {tab === 'activity' && <CaseIntelligence item={c} view="audit" onNavigate={setTab} />}
              {['file', 'assistant'].includes(tab) && (
                <CaseIntelligence
                  item={c}
                  view={tab}
                  onNavigate={(key) =>
                    setTab(key === 'journey' ? 'quotes' : key === 'audit' ? 'activity' : key)
                  }
                />
              )}
            </section>
          )}
        </div>
        <BottomSheet
          open={medicalPrompt}
          onClose={() => setMedicalPrompt(false)}
          container={dialog.current}
          title="Reveal medical statements"
          description="Medical text stays inside this case and is hidden by default."
          detent="auto"
        >
          <Reauthenticate
            title="Verify to view medical statements."
            actionLabel="Verify medical access"
            onVerified={async (proof) => {
              await api(`/cases/${id}/medical-access`, {
                method: 'POST',
                headers: { 'X-Step-Up': proof },
              });
              medicalRevealed.current = true;
              await refresh();
              setMedicalPrompt(false);
            }}
          />
        </BottomSheet>
        <BottomSheet
          open={pausePrompt}
          onClose={() => setPausePrompt(false)}
          container={dialog.current}
          title="Pause this case"
          description={
            c?.state === 'AWAIT_BROKER_RELEASE'
              ? 'Record why RFQ release should pause. Resume and release when ready.'
              : 'Queued work pauses while you review the case. Existing partner requests remain recorded.'
          }
          detent="auto"
        >
          <TextArea
            label="Reason for pausing"
            minLength={10}
            value={pauseReason}
            onChange={(event) => setPauseReason(event.target.value)}
          />
          <button
            className="button primary"
            disabled={busy || pauseReason.trim().length < 10}
            onClick={async () => {
              if (await action('pause', { reason: pauseReason.trim() })) {
                setPausePrompt(false);
                setPauseReason('');
              }
            }}
          >
            Confirm pause
          </button>
        </BottomSheet>
        <footer className="panel-footer">
          <BottomSheet
            open={complaintPrompt}
            onClose={() => setComplaintPrompt(false)}
            container={dialog.current}
            title="Record a complaint"
            description="This pauses agent work and assigns a compliance owner."
            detent="auto"
          >
            <TextArea
              label="Complaint details"
              minLength={20}
              maxLength={1000}
              value={complaintReason}
              onChange={(e) => setComplaintReason(e.target.value)}
            />
            <button
              className="button primary"
              disabled={busy || complaintReason.trim().length < 20}
              onClick={async () => {
                if (await action('complaint', { reason: complaintReason.trim() }))
                  setComplaintPrompt(false);
              }}
            >
              Record complaint and pause work
            </button>
          </BottomSheet>
          <ShieldCheck size={13} />
          <span>Grounded in facts. Approved by a human.</span>
          <span>DEMO</span>
        </footer>
      </div>
    </dialog>
  );
}

function ChartNotice() {
  return <AlertTriangle size={18} />;
}
