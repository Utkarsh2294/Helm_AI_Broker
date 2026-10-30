import { useInfiniteQuery } from '@tanstack/react-query';
import { useLocation, useNavigate } from 'react-router-dom';
import React, { useCallback, useEffect, useState, useRef, lazy, Suspense } from 'react';
const Governance = lazy(() => import('./components/Governance'));
const DemoShowcase = lazy(() => import('./components/DemoShowcase'));
import {
  ArrowUpRight,
  Search,
  SlidersHorizontal,
  Plus,
  Users,
  ClipboardCheck,
  Clock3,
  CheckCheck,
  ShieldCheck,
  FileSearch,
  BrainCircuit,
} from 'lucide-react';
import { api, label } from './api';
const CasePanel = lazy(() => import('./case-panel'));
import CommandPalette from './components/CommandPalette';
import QuickLook from './components/QuickLook';
import { CaseAssistant } from './components/CaseIntelligence';

const states = {
  FACTFIND_REVIEW: 'Fact-find review',
  AWAIT_BROKER_RELEASE: 'Ready for RFQ',
  QUOTES_PENDING: 'Awaiting quotations',
  BROKER_REVIEW: 'Ready to compare',
  AWAIT_APPROVAL: 'Approval needed',
  PUBLISHED: 'Demo delivered',
  PAUSED_NEEDS_HUMAN: 'Needs your attention',
  COMPLAINT_FLAGGED: 'Complaint · on hold',
  NEEDS_INFO: 'Missing information',
};
export const stateLabel = (state) => states[state] || label(state);
export function Status({ state }) {
  const tone = ['PUBLISHED', 'BROKER_REVIEW'].includes(state)
    ? 'green'
    : ['QUOTES_PENDING', 'AWAIT_APPROVAL', 'AWAIT_BROKER_RELEASE'].includes(state)
      ? 'amber'
      : ['COMPLAINT_FLAGGED', 'PAUSED_NEEDS_HUMAN'].includes(state)
        ? 'red'
        : '';
  return (
    <span className={`state-badge ${tone}`}>
      <span />
      {stateLabel(state)}
    </span>
  );
}

export default function Workspace({ page, user, setPage }) {
  const location = useLocation(),
    navigate = useNavigate();
  const selected = location.pathname.startsWith('/case/')
    ? decodeURIComponent(location.pathname.slice(6))
    : null;
  const setSelected = (id) => navigate(id ? `/case/${encodeURIComponent(id)}` : '/queue');
  const [error, setError] = useState('');
  const [sort, setSort] = useState('newest'),
    [assignee, setAssignee] = useState(''),
    [priority, setPriority] = useState('');
  const moreRef = useRef(null);
  const [query, setQuery] = useState(''),
    [filter, setFilter] = useState('');
  const [creating, setCreating] = useState(false),
    [partners, setPartners] = useState([]);
  const [quick, setQuick] = useState(null);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const listing = useInfiniteQuery({
    queryKey: ['cases', user.id, query, filter, sort, assignee, priority],
    initialPageParam: '',
    queryFn: ({ pageParam }) =>
      api(
        `/cases?limit=50&cursor=${encodeURIComponent(pageParam)}&q=${encodeURIComponent(query)}&state=${filter}&sort=${sort}&assignee=${assignee}&priority=${priority}`,
      ),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    refetchInterval: 3000,
  });
  const cases = listing.data?.pages.flatMap((p) => p.items) || [],
    loading = listing.isPending;
  const refresh = useCallback(async () => {
    await listing.refetch();
  }, [listing.refetch]);
  useEffect(() => {
    if (!moreRef.current || !listing.hasNextPage) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !listing.isFetchingNextPage) listing.fetchNextPage();
      },
      { rootMargin: '150px' },
    );
    observer.observe(moreRef.current);
    return () => observer.disconnect();
  }, [listing.hasNextPage, listing.isFetchingNextPage, listing.fetchNextPage]);
  useEffect(() => {
    let active = true;
    const load = page === 'partners' ? api('/partners') : null;
    load
      ?.then((v) => {
        if (active) setPartners(v);
      })
      .catch((e) => setError(e.message));
    return () => {
      active = false;
    };
  }, [page, cases.length]);
  const summary = listing.data?.pages[0]?.summary || {};
  const review = [
    'FACTFIND_REVIEW',
    'BROKER_REVIEW',
    'AWAIT_APPROVAL',
    'PAUSED_NEEDS_HUMAN',
  ].reduce((sum, state) => sum + (summary[state] || 0), 0);
  const pending = summary.QUOTES_PENDING || 0,
    delivered = summary.PUBLISHED || 0;
  const totalCases = Object.values(summary).reduce((sum, count) => sum + count, 0),
    matchedCases = listing.data?.pages[0]?.total || 0;
  const openCases = totalCases - delivered - (summary.CLOSED || 0);
  const visible = cases.filter(
    (c) =>
      (!query || `${c.name} ${c.postcode}`.toLowerCase().includes(query.toLowerCase())) &&
      (!filter || c.state === filter),
  );
  async function newRequest() {
    setCreating(true);
    setError('');
    try {
      const c = await api('/demo/journeys', {
        method: 'POST',
      });
      await refresh();
      setSelected(c.id);
    } catch (e) {
      setError(e.message);
    } finally {
      setCreating(false);
    }
  }
  const headings = {
    workspace: [
      'YOUR DAY, AT A GLANCE',
      'Good advice starts with clarity.',
      'A little less admin. A little more time for your clients.',
    ],
    partners: [
      'YOUR DEMO PANEL',
      'A wider view of the market.',
      'Five fictional insurers, connected through a single quotation workflow.',
    ],
    learning: [
      'BETTER, WITH EVERY DECISION',
      'Your judgement makes us better.',
      'Turn broker feedback into measured, human-reviewed improvements.',
    ],
    demo: [
      'THE COMPLETE DEMONSTRATION',
      'See the whole journey.',
      'Fictional documents, human review and a pilot-readiness rehearsal.',
    ],
  };
  const [eyebrow, title, subtitle] = headings[page];
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">{eyebrow}</span>
          <h1>{title}</h1>
          <p className="muted">{subtitle}</p>
        </div>
        {page === 'workspace' && user.role === 'authorised_broker' && (
          <button className="button primary" onClick={newRequest} disabled={creating}>
            <Plus size={16} />
            {creating ? 'Starting agents…' : 'Start automatic demo'}
          </button>
        )}
      </div>
      {listing.error && (
        <p role="alert" className="error">
          {listing.error.message}
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}{' '}
          <button className="text-button" onClick={refresh}>
            Retry
          </button>
        </p>
      )}
      {page === 'workspace' && (
        <>
          <div className="workspace-assistant-toggle">
            <button
              className="button small"
              aria-expanded={assistantOpen}
              onClick={() => setAssistantOpen((value) => !value)}
            >
              Workspace assistant
            </button>
            <span className="muted">
              Open a case to see its digital file, agent work and reasons.
            </span>
          </div>
          {assistantOpen && <CaseAssistant onOpenCase={setSelected} />}
          <div className="metrics-grid">
            {[
              [Users, 'Open cases', openCases, 'People, not paperwork', 'neutral'],
              [ClipboardCheck, 'Your review', review, 'Ready for your expertise', 'green'],
              [Clock3, 'With partners', pending, 'Quotations in progress', 'amber'],
              [CheckCheck, 'Demo delivered', delivered, 'Approved by a human', 'neutral'],
            ].map(([Icon, name, value, detail, tone]) => (
              <div className={`metric ${tone}`} key={name}>
                <div>
                  <span>{name}</span>
                  <Icon size={17} />
                </div>
                <strong>{value.toString().padStart(2, '0')}</strong>
                <small>{detail}</small>
              </div>
            ))}
          </div>
          <section className="case-section">
            <div className="section-header">
              <div>
                <h2>Your casework</h2>
                <span className="count-badge">{matchedCases}</span>
              </div>
              <span className="table-hint">
                <span className="status-dot" /> Updated as your agents work
              </span>
            </div>
            <div className="table-toolbar">
              <div className="filter-tabs">
                <button className={!filter ? 'active' : ''} onClick={() => setFilter('')}>
                  All cases<span>{totalCases}</span>
                </button>
                <button
                  className={filter === 'FACTFIND_REVIEW' ? 'active' : ''}
                  onClick={() => setFilter('FACTFIND_REVIEW')}
                >
                  Fact-find
                </button>
                <button
                  className={filter === 'BROKER_REVIEW' ? 'active' : ''}
                  onClick={() => setFilter('BROKER_REVIEW')}
                >
                  Compare
                </button>
                <button
                  className={filter === 'AWAIT_APPROVAL' ? 'active' : ''}
                  onClick={() => setFilter('AWAIT_APPROVAL')}
                >
                  To approve
                </button>
              </div>
              <div className="table-controls">
                <label className="search-field">
                  <Search size={15} />
                  <input
                    aria-label="Search cases"
                    placeholder="Search your cases…"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                </label>
                <label className="filter-select">
                  <SlidersHorizontal size={15} />
                  <select
                    aria-label="Filter case status"
                    value={filter}
                    onChange={(e) => setFilter(e.target.value)}
                  >
                    <option value="">All statuses</option>
                    {Object.keys(states).map((s) => (
                      <option value={s} key={s}>
                        {stateLabel(s)}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Sort
                  <select
                    aria-label="Sort cases"
                    value={sort}
                    onChange={(e) => setSort(e.target.value)}
                  >
                    <option value="newest">Newest first</option>
                    <option value="oldest">Oldest first</option>
                    <option value="name">Client name</option>
                  </select>
                </label>
                <label>
                  Assignee
                  <select
                    aria-label="Filter assignee"
                    value={assignee}
                    onChange={(e) => setAssignee(e.target.value)}
                  >
                    <option value="">Everyone</option>
                    <option value="me">Assigned to me</option>
                    <option value="unassigned">Unassigned</option>
                  </select>
                </label>
                <label>
                  Priority
                  <select
                    aria-label="Filter priority"
                    value={priority}
                    onChange={(e) => setPriority(e.target.value)}
                  >
                    <option value="">All priorities</option>
                    <option value="urgent">Urgent</option>
                    <option value="normal">Normal</option>
                  </select>
                </label>
              </div>
            </div>
            <div className="table-scroll">
              <table className="case-table">
                <thead>
                  <tr>
                    <th>CLIENT</th>
                    <th>COVER TYPE</th>
                    <th>STATUS</th>
                    <th>REQUEST</th>
                    <th>CASE ACTIONS</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((c, i) => (
                    <tr key={c.id} data-case-id={c.id}>
                      <td>
                        <button
                          className="client-button"
                          onKeyDown={(e) => {
                            if (e.key === ' ') {
                              e.preventDefault();
                              setQuick(c);
                            }
                          }}
                          onClick={() => setSelected(c.id)}
                        >
                          <span className={`client-avatar avatar-${i % 4}`}>
                            {c.name
                              .split(' ')
                              .filter((n) => n !== '&')
                              .slice(0, 2)
                              .map((n) => n[0])
                              .join('')}
                          </span>
                          <span>
                            <strong>{c.name}</strong>
                            <small>{c.postcode} · Fictional client</small>
                          </span>
                        </button>
                      </td>
                      <td>
                        <span className="cover-type">{label(c.cover_type)}</span>
                      </td>
                      <td>
                        <Status state={c.state} />
                        {c.workflow === 'fictional-two-decisions-v1' && (
                          <small className="block case-agent-summary">
                            {c.state === 'BROKER_REVIEW'
                              ? 'Your decision 1: choose and rank'
                              : c.state === 'AWAIT_APPROVAL'
                                ? 'Your decision 2: final sign-off'
                                : c.state === 'PUBLISHED'
                                  ? 'Signed demo · learning runs automatically'
                                  : 'Agents prepare automatically · open for reasons'}
                          </small>
                        )}
                      </td>
                      <td className="request-date">
                        <span>
                          {new Intl.DateTimeFormat('en-GB', {
                            day: 'numeric',
                            month: 'short',
                          }).format(new Date(c.created_at))}
                        </span>
                        <small>{c.assigned_to ? 'Assigned' : 'Unassigned'}</small>
                      </td>
                      <td>
                        <div className="case-row-actions">
                          <button
                            className="button small case-audit-button"
                            aria-label={`Audit trail for ${c.name}`}
                            onClick={() => navigate(`/case/${encodeURIComponent(c.id)}?view=audit`)}
                          >
                            Audit trail
                          </button>
                          <button
                            className="open-case"
                            aria-label={`Open ${c.name}`}
                            onClick={() => setSelected(c.id)}
                          >
                            <ArrowUpRight size={16} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!visible.length && (
                <div className="empty-state">
                  <FileSearch size={25} />
                  <h3>{loading ? 'Loading your cases…' : 'No matching cases'}</h3>
                  <p>
                    {loading
                      ? 'Getting your workspace ready.'
                      : 'Try another search or change the status filter.'}
                  </p>
                </div>
              )}
            </div>
            <div className="table-bottom">
              <span>
                Showing {visible.length} of {listing.data?.pages[0]?.total || 0} cases
              </span>
              <span>One case. A complete picture.</span>
            </div>
          </section>
          {listing.hasNextPage && (
            <button
              ref={moreRef}
              className="button"
              disabled={listing.isFetchingNextPage}
              onClick={() => listing.fetchNextPage()}
            >
              Load more cases
            </button>
          )}
          <div className="workspace-bottom">
            <div className="human-banner">
              <span className="banner-icon">
                <ShieldCheck size={24} strokeWidth={1.5} />
              </span>
              <div>
                <h3>Intelligent support. Human assurance.</h3>
                <p>
                  Your agents gather, compare and prepare. Every recommendation is yours to approve.
                </p>
              </div>
              <span className="subtle-badge">HUMAN IN THE LOOP</span>
            </div>
            <button className="learning-link" onClick={() => setPage('learning')}>
              <BrainCircuit size={22} />
              <span>
                <strong>A little better, every day.</strong>
                <small>Explore feedback & learning</small>
              </span>
              <ArrowUpRight size={18} />
            </button>
          </div>
        </>
      )}
      {page === 'partners' && (
        <section className="surface">
          <div className="section-header">
            <h2>Partner directory</h2>
            <span className="subtle-badge">FICTIONAL PANEL</span>
          </div>
          <div className="table-scroll">
            <table className="case-table">
              <thead>
                <tr>
                  <th>PARTNER</th>
                  <th>DEMO REGISTER STATUS</th>
                  <th>TERMS OF BUSINESS</th>
                  <th>CHANNEL</th>
                </tr>
              </thead>
              <tbody>
                {partners.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <strong>{p.name}</strong>
                      <small className="block muted">Fictional insurer</small>
                    </td>
                    <td>
                      <span className="state-badge green">
                        <span />
                        {label(p.fca_status)}
                      </span>
                    </td>
                    <td>{label(p.toba_status)}</td>
                    <td>Partner simulator</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="surface-note">
            These are synthetic records. Live register checks and partner API contracts remain to be
            verified.
          </p>
        </section>
      )}
      {page === 'learning' && (
        <Suspense fallback={<p role="status">Loading learning records…</p>}>
          <Governance user={user} />
        </Suspense>
      )}
      {page === 'demo' && (
        <Suspense fallback={<p role="status">Loading pilot showcase…</p>}>
          <DemoShowcase user={user} />
        </Suspense>
      )}
      <CommandPalette cases={cases} onCase={setSelected} onPage={setPage} />
      {quick && (
        <QuickLook
          item={quick}
          onClose={() => setQuick(null)}
          onOpen={(id) => {
            setQuick(null);
            setSelected(id);
          }}
        />
      )}
      {selected && (
        <Suspense fallback={<p role="status">Opening case…</p>}>
          <CasePanel
            key={`${selected}:${location.search}`}
            id={selected}
            initialView={
              new URLSearchParams(location.search).get('view') === 'audit' ? 'audit' : 'journey'
            }
            user={user}
            onClose={() => {
              setSelected(null);
              refresh();
            }}
          />
        </Suspense>
      )}
      <span className="sr-only" aria-live="polite">
        {creating ? 'Creating a demo request' : ''}
      </span>
    </>
  );
}
