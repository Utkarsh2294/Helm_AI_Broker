import React, { useCallback, useEffect, useState } from 'react';
import { ArrowRight, ArrowUpRight, Search, SlidersHorizontal, Plus, Users, ClipboardCheck, Clock3, CheckCheck, Sparkles, ShieldCheck, FileSearch, Send, ChartNoAxesCombined, BookOpenCheck, BrainCircuit, ChevronRight, RefreshCw, History } from 'lucide-react';
import { api, label } from './api';
import CasePanel from './case-panel';
import CommandPalette from './components/CommandPalette';
import QuickLook from './components/QuickLook';

const icons = [FileSearch, Send, ChartNoAxesCombined, BookOpenCheck, BrainCircuit];
const names = ['Research & fact-find', 'Partner quotations', 'Policy ranking', 'Review & compliance', 'Learning & insights'];
const descriptions = ['Builds a sourced demands-and-needs record. Preserves medical statements verbatim and flags missing information.', 'Requests quotes from all eligible fictional partners. Tracks replies, declines and requests for human clarification.', 'Computes scores, exclusions, tie bands, stability and weight-shift analysis. Commission is excluded from ranking.', 'Checks your selections, collects feedback and drafts a suitability pack. Approval always requires a broker.', 'Evaluates undisputed choices on held-out cases. Produces bounded proposals and never activates them.'];
const states = { FACTFIND_REVIEW: 'Fact-find review', AWAIT_BROKER_RELEASE: 'Ready for RFQ', QUOTES_PENDING: 'Awaiting quotations', BROKER_REVIEW: 'Ready to compare', AWAIT_APPROVAL: 'Approval needed', PUBLISHED: 'Demo delivered', PAUSED_NEEDS_HUMAN: 'Needs your attention', COMPLAINT_FLAGGED: 'Complaint · on hold', NEEDS_INFO: 'Missing information' };
export const stateLabel = state => states[state] || label(state);
export function Status({ state }) {
  const tone = ['PUBLISHED', 'BROKER_REVIEW'].includes(state) ? 'green' : ['QUOTES_PENDING', 'AWAIT_APPROVAL', 'AWAIT_BROKER_RELEASE'].includes(state) ? 'amber' : ['COMPLAINT_FLAGGED', 'PAUSED_NEEDS_HUMAN'].includes(state) ? 'red' : '';
  return <span className={`state-badge ${tone}`}><span/>{stateLabel(state)}</span>;
}

export default function Workspace({ page, user, setPage }) {
  const [cases, setCases] = useState([]), [error, setError] = useState(''), [loading, setLoading] = useState(true);
  const [query, setQuery] = useState(''), [filter, setFilter] = useState(''), [selected, setSelected] = useState(null);
  const [creating, setCreating] = useState(false), [partners, setPartners] = useState([]), [models, setModels] = useState([]);
  const [evaluating, setEvaluating] = useState(false), [auditCases, setAuditCases] = useState([]);
  const [quick, setQuick] = useState(null);
  const refresh = useCallback(async () => {
    try { setCases(await api('/cases')); setError(''); } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { refresh(); const timer = setInterval(refresh, 3000); return () => clearInterval(timer); }, [refresh]);
  useEffect(() => {
    let active = true;
    const load = page === 'partners' ? api('/partners') : page === 'learning' ? api('/models') : page === 'audit' ? Promise.all(cases.map(c => api(`/cases/${c.id}`))) : null;
    load?.then(v => { if (active) (page === 'partners' ? setPartners : page === 'learning' ? setModels : setAuditCases)(v); }).catch(e => setError(e.message));
    return () => { active = false; };
  }, [page, cases.length]);
  const review = cases.filter(c => ['FACTFIND_REVIEW', 'BROKER_REVIEW', 'AWAIT_APPROVAL', 'PAUSED_NEEDS_HUMAN'].includes(c.state)).length;
  const pending = cases.filter(c => c.state === 'QUOTES_PENDING').length, delivered = cases.filter(c => c.state === 'PUBLISHED').length;
  const visible = cases.filter(c => (!query || `${c.name} ${c.postcode}`.toLowerCase().includes(query.toLowerCase())) && (!filter || c.state === filter));
  async function newRequest() {
    setCreating(true); setError('');
    try {
      const c = await api('/demo/requests', { method: 'POST', body: { id: `demo-${crypto.randomUUID()}`, name: `Demo applicant ${cases.length + 1}`, cover_type: 'individual', needs: { budget_annual_pence: 180000, coverage: { cancer: { level: 3, must_have: true }, outpatient: { level: 3 } } } } });
      await refresh(); setSelected(c.id);
    } catch (e) { setError(e.message); } finally { setCreating(false); }
  }
  async function evaluate() {
    setEvaluating(true); setError('');
    try { await api('/models/evaluate', { method: 'POST' }); setModels(await api('/models')); }
    catch (e) { setError(e.message); } finally { setEvaluating(false); }
  }
  const headings = {
    workspace: ['YOUR DAY, AT A GLANCE', 'Good advice starts with clarity.', 'A little less admin. A little more time for your clients.'],
    agents: ['INTELLIGENCE, WITH DIRECTION', 'Meet your supporting cast.', 'Five specialists. One connected workflow. You make the final call.'],
    partners: ['YOUR DEMO PANEL', 'A wider view of the market.', 'Five fictional insurers, connected through a single quotation workflow.'],
    learning: ['BETTER, WITH EVERY DECISION', 'Your judgement makes us better.', 'Turn broker feedback into measured, human-reviewed improvements.'],
    audit: ['EVERY STEP, ACCOUNTED FOR', 'A clear trail of every decision.', 'Follow the facts, approvals and hand-offs behind each case.'],
  };
  const [eyebrow, title, subtitle] = headings[page];
  return <><div className="page-heading"><div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1><p className="muted">{subtitle}</p></div>{page === 'workspace' && user.role === 'authorised_broker' && <button className="button primary" onClick={newRequest} disabled={creating}><Plus size={16}/>{creating ? 'Creating…' : 'New demo request'}</button>}{page === 'learning' && <button className="button primary" onClick={evaluate} disabled={evaluating}><RefreshCw size={15}/>{evaluating ? 'Evaluating…' : 'Run feedback evaluation'}</button>}</div>
    {error && <p role="alert" className="error">{error} <button className="text-button" onClick={refresh}>Retry</button></p>}
    {page === 'workspace' && <>
      <div className="metrics-grid">{[[Users, 'Open cases', cases.length - delivered, 'People, not paperwork', 'neutral'], [ClipboardCheck, 'Your review', review, 'Ready for your expertise', 'green'], [Clock3, 'With partners', pending, 'Quotations in progress', 'amber'], [CheckCheck, 'Demo delivered', delivered, 'Approved by a human', 'neutral']].map(([Icon, name, value, detail, tone]) => <div className={`metric ${tone}`} key={name}><div><span>{name}</span><Icon size={17}/></div><strong>{value.toString().padStart(2, '0')}</strong><small>{detail}</small></div>)}</div>
      <section className="pipeline-section"><div className="section-header"><div><Sparkles size={15}/><h3>Your team, working in sync</h3><span className="subtle-badge">5 SPECIALIST AGENTS</span></div><button className="text-button" onClick={() => setPage('agents')}>Meet the team<ArrowUpRight size={14}/></button></div>
        <div className="pipeline-steps">{names.map((name, i) => { const Icon = icons[i]; return <React.Fragment key={name}><button className="pipeline-step" onClick={() => setPage(i === 4 ? 'learning' : 'agents')}><span className="pipeline-icon"><Icon size={20} strokeWidth={1.5}/></span><div><small>AGENT 0{i + 1}</small><strong>{['Research', 'Quotation', 'Ranking', 'Review', 'Learning'][i]}</strong><span>{['Facts, with sources', 'All eligible partners', 'Explain every score', 'Your final decision', 'Feedback, thoughtfully'][i]}</span></div></button>{i < 4 && <ChevronRight className="pipeline-chevron" size={14}/>}</React.Fragment>; })}</div>
      </section>
      <section className="case-section"><div className="section-header"><div><h3>Your casework</h3><span className="count-badge">{cases.length}</span></div><span className="table-hint"><span className="status-dot"/> Updated as your agents work</span></div>
        <div className="table-toolbar"><div className="filter-tabs"><button className={!filter ? 'active' : ''} onClick={() => setFilter('')}>All cases<span>{cases.length}</span></button><button className={filter === 'FACTFIND_REVIEW' ? 'active' : ''} onClick={() => setFilter('FACTFIND_REVIEW')}>Fact-find</button><button className={filter === 'BROKER_REVIEW' ? 'active' : ''} onClick={() => setFilter('BROKER_REVIEW')}>Compare</button><button className={filter === 'AWAIT_APPROVAL' ? 'active' : ''} onClick={() => setFilter('AWAIT_APPROVAL')}>To approve</button></div><div className="table-controls"><label className="search-field"><Search size={15}/><input aria-label="Search cases" placeholder="Search your cases…" value={query} onChange={e => setQuery(e.target.value)}/></label><label className="filter-select"><SlidersHorizontal size={15}/><select aria-label="Filter case status" value={filter} onChange={e => setFilter(e.target.value)}><option value="">All statuses</option>{Object.keys(states).map(s => <option value={s} key={s}>{stateLabel(s)}</option>)}</select></label></div></div>
        <div className="table-scroll"><table className="case-table"><thead><tr><th>CLIENT</th><th>COVER TYPE</th><th>STATUS</th><th>REQUEST</th><th aria-label="Open case"/></tr></thead><tbody>{visible.map((c, i) => <tr key={c.id}><td><button className="client-button" onClick={() => setSelected(c.id)}><span className={`client-avatar avatar-${i % 4}`}>{c.name.split(' ').filter(n => n !== '&').slice(0, 2).map(n => n[0]).join('')}</span><span><strong>{c.name}</strong><small>{c.postcode} · Fictional client</small></span></button></td><td><span className="cover-type">{label(c.cover_type)}</span></td><td><Status state={c.state}/></td><td className="request-date"><span>{new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' }).format(new Date(c.created_at))}</span><small>{c.assigned_to ? 'Assigned' : 'Unassigned'}</small></td><td><button className="open-case" aria-label={`Open ${c.name}`} onClick={() => setSelected(c.id)}><ArrowUpRight size={16}/></button></td></tr>)}</tbody></table>{!visible.length && <div className="empty-state"><FileSearch size={25}/><h3>{loading ? 'Loading your cases…' : 'No matching cases'}</h3><p>{loading ? 'Getting your workspace ready.' : 'Try another search or change the status filter.'}</p></div>}</div><div className="table-bottom"><span>Showing {visible.length} of {cases.length} cases</span><span>One case. A complete picture.</span></div>
      </section>
      <div className="workspace-bottom"><div className="human-banner"><span className="banner-icon"><ShieldCheck size={24} strokeWidth={1.5}/></span><div><h3>Intelligent support. Human assurance.</h3><p>Your agents gather, compare and prepare. Every recommendation is yours to approve.</p></div><span className="subtle-badge">HUMAN IN THE LOOP</span></div><button className="learning-link" onClick={() => setPage('learning')}><BrainCircuit size={22}/><span><strong>A little better, every day.</strong><small>Explore feedback & learning</small></span><ArrowUpRight size={18}/></button></div>
    </>}
    {page === 'agents' && <><div className="agent-grid">{names.map((name, i) => { const Icon = icons[i]; return <article className="agent-card" key={name}><div className="agent-card-top"><span className="pipeline-icon"><Icon size={25} strokeWidth={1.4}/></span><span className="eyebrow">AGENT 0{i + 1}</span></div><h2>{name}</h2><p className="agent-description">{descriptions[i]}</p><button className="text-button" onClick={() => setPage(i === 4 ? 'learning' : 'workspace')}>{i === 4 ? 'View learning' : 'View casework'}<ArrowRight size={15}/></button></article>; })}</div><p className="footnote"><ShieldCheck size={14}/> Demo agents run grounded local code. No consumer medical text is sent to a language model.</p></>}
    {page === 'partners' && <section className="surface"><div className="section-header"><h3>Partner directory</h3><span className="subtle-badge">FICTIONAL PANEL</span></div><div className="table-scroll"><table className="case-table"><thead><tr><th>PARTNER</th><th>DEMO REGISTER STATUS</th><th>TERMS OF BUSINESS</th><th>CHANNEL</th></tr></thead><tbody>{partners.map(p => <tr key={p.id}><td><strong>{p.name}</strong><small className="block muted">Fictional insurer</small></td><td><span className="state-badge green"><span/>{label(p.fca_status)}</span></td><td>{label(p.toba_status)}</td><td>Partner simulator</td></tr>)}</tbody></table></div><p className="surface-note">These are synthetic records. Live register checks and partner API contracts remain to be verified.</p></section>}
    {page === 'learning' && <><div className="learning-summary"><BrainCircuit size={32} strokeWidth={1.2}/><div><h2>Learn carefully. Improve deliberately.</h2><p>At least 30 comparisons across three cases are needed. Disputed selections go to human review. Changes require compliance and lead-broker approval, then shadow evaluation.</p></div></div>{!models.length ? <div className="empty-state surface"><ChartNoAxesCombined size={32}/><h2>Good learning starts with evidence.</h2><p>Review cases and share feedback, then run an evaluation.</p></div> : <div className="model-list">{models.map(m => <article className="surface model-report" key={m.id}><div className="section-header"><h3>{m.status === 'proposed' ? 'Model change proposal' : 'More feedback needed'}</h3><span className="subtle-badge">{new Date(m.created_at).toLocaleDateString('en-GB')}</span></div><p className="muted">{m.comparison_count} comparisons · {m.disputed.length} disputed selections · No weights automatically applied</p><div className="weight-bars">{Object.entries(m.weights).map(([name, w]) => <div key={name}><span>{label(name)}</span><div className="bar-track"><div style={{ width: `${w * 100}%` }}/></div><strong>{(w * 100).toFixed(1)}%</strong></div>)}</div>{m.champion_metrics && <p className="muted">Held-out NDCG@3: {m.champion_metrics.ndcg3.toFixed(3)} → {m.challenger_metrics.ndcg3.toFixed(3)}</p>}<p className="footnote"><ShieldCheck size={14}/> Activation is intentionally unavailable in this demo.</p></article>)}</div>}</>}
    {page === 'audit' && <section className="surface"><div className="section-header"><h3>Case activity</h3><button className="text-button" onClick={() => Promise.all(cases.map(c => api(`/cases/${c.id}`))).then(setAuditCases).catch(e => setError(e.message))}><RefreshCw size={14}/>Refresh</button></div>{auditCases.flatMap(c => c.events.map(e => ({ ...e, case: c }))).sort((a, b) => b.created_at.localeCompare(a.created_at)).map(e => <button className="audit-row" key={`${e.case.id}-${e.seq}`} onClick={() => setSelected(e.case.id)}><span className="audit-marker"><CheckCheck size={15}/></span><div><strong>{label(e.type)}</strong><span>{e.case.name} · {e.actor.startsWith('agent') ? label(e.actor.replace(':', ' ')) : e.actor.startsWith('broker') ? 'Broker' : 'System'}</span></div><time>{new Date(e.created_at).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}</time><ChevronRight size={15}/></button>)}{!auditCases.length && <div className="empty-state"><History size={25}/><p>Loading activity…</p></div>}</section>}
    <CommandPalette cases={cases} onCase={setSelected} onPage={setPage}/>
    {quick && <QuickLook item={quick} onClose={() => setQuick(null)} onOpen={id => { setQuick(null); setSelected(id); }}/>}<button className="sr-only" onClick={() => cases[0] && setQuick(cases[0])} onKeyDown={e => { if (e.key === ' ') { e.preventDefault(); cases[0] && setQuick(cases[0]); } }}>Quick look first case</button>
    {selected && <CasePanel id={selected} user={user} onClose={() => { setSelected(null); refresh(); }}/>}<span className="sr-only" aria-live="polite">{creating ? 'Creating a demo request' : ''}</span>
  </>;
}
