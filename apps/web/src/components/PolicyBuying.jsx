import React, { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useInfiniteQuery } from '@tanstack/react-query';
import { ArrowUpRight, FileCheck2 } from 'lucide-react';
import { api, money } from '../api';
import './policy-buying.css';
import PolicyBuyingCase from './PolicyBuyingCase';

export const buyingStages = [
  'QUOTE_SELECTED',
  'IPID_DRAFTING',
  'AWAITING_IPID_CONFIRMATION',
  'UNDERWRITING_IN_PROGRESS',
  'AWAITING_BANKING_DETAILS',
  'SUBMISSION_PACKAGE_READY',
  'SUBMITTED_TO_INSURER',
  'POLICY_ISSUED',
];
export const stageLabels = [
  'Quote selected',
  'Prepare IPID',
  'Consumer confirmation',
  'Underwriting',
  'Banking details',
  'Review package',
  'Submitted',
  'Policy issued',
];

export default function PolicyBuying({ user, closed = false }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [starting, setStarting] = useState(false),
    [startError, setStartError] = useState('');
  async function startExample(basis) {
    setStarting(true);
    setStartError('');
    try {
      const item = await api(`/demo/journeys?underwriting=${basis}`, { method: 'POST' });
      navigate(`/case/${item.id}`);
    } catch (cause) {
      setStartError(cause.message);
    } finally {
      setStarting(false);
    }
  }
  const caseId = location.pathname.startsWith('/policy-buying/cases/')
    ? decodeURIComponent(location.pathname.slice('/policy-buying/cases/'.length))
    : null;
  const query = useInfiniteQuery({
    queryKey: ['policy-buying', user.id, closed],
    initialPageParam: 0,
    queryFn: ({ pageParam }) => api(`/policy-buying?offset=${pageParam}&closed=${closed}`),
    getNextPageParam: (last) => last.next_offset ?? undefined,
    refetchInterval: 5000,
  });
  if (caseId) return <PolicyBuyingCase caseId={caseId} user={user} />;
  const rows = query.data?.pages.flatMap((page) => page.items) || [];
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">FROM RECOMMENDATION TO COMPLETION</span>
          <h1>{closed ? 'Closed Cases' : 'Policy Buying'}</h1>
          <p className="muted">
            One selected quote. Every document, response and approval in one place.
          </p>
        </div>
      </div>
      <p className="pb-demo">
        <strong>Demo only.</strong> Consumer responses and insurer submission are simulated. No real
        policy is purchased.
      </p>
      {!closed && ['authorised_broker', 'lead_broker'].includes(user.role) && (
        <div className="assistant-toolbar">
          <button
            className="button small"
            disabled={starting}
            onClick={() => startExample('moratorium')}
          >
            Start Moratorium demo
          </button>
          <button className="button small" disabled={starting} onClick={() => startExample('fmu')}>
            Start FMU demo
          </button>
          <p>
            These create fictional fact-finds. Policy selection and final recommendation sign-off
            remain your decisions.
          </p>
        </div>
      )}
      {startError && (
        <p className="error" role="alert">
          {startError}
        </p>
      )}
      {query.error && (
        <p className="error" role="alert">
          {query.error.message}
          <button className="text-button" onClick={() => query.refetch()}>
            Retry
          </button>
        </p>
      )}
      <section aria-label="Policy Buying pipeline" className="pb-pipeline">
        <div className="section-header">
          <h2>{closed ? 'Successfully issued demo policies' : 'In progress'}</h2>
          <span className="count-badge">{query.data?.pages[0]?.total || 0}</span>
        </div>
        {query.isPending ? (
          <p role="status">Loading buying cases…</p>
        ) : rows.length ? (
          <ul className="pb-list">
            {rows.map((row) => (
              <li key={row.id} className={row.closed_at ? 'pb-success' : ''}>
                <div>
                  <Link className="pb-client" to={`/policy-buying/cases/${row.case_id}`}>
                    {row.client}
                    <ArrowUpRight size={16} />
                  </Link>
                  {row.policy_number && (
                    <p className="state-badge green">Demo policy issued · {row.policy_number}</p>
                  )}
                  <p>
                    {row.plan.name} · {row.plan.insurerId}
                  </p>
                  <small>{money(row.plan.annualPremiumPence)} / year, including IPT</small>
                </div>
                <div>
                  <strong>{stageLabels[buyingStages.indexOf(row.stage)]}</strong>
                  <progress
                    aria-label={`${row.client} buying progress`}
                    max={8}
                    value={buyingStages.indexOf(row.stage) + 1}
                  />
                  <small>{new Date(row.last_activity).toLocaleString('en-GB')}</small>
                </div>
                <Link className="button small" to={`/policy-buying/cases/${row.case_id}`}>
                  {row.updates ? `${row.updates} updates` : 'Open case'}
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <div className="empty-state">
            <FileCheck2 size={28} />
            <h3>No cases in Policy Buying yet</h3>
            <p>Open a published recommendation and simulate the consumer choosing one plan.</p>
            <Link className="button small" to="/queue">
              Open workspace
            </Link>
          </div>
        )}
        {query.hasNextPage && (
          <button
            className="button"
            disabled={query.isFetchingNextPage}
            onClick={() => query.fetchNextPage()}
          >
            Load more cases
          </button>
        )}
      </section>
    </>
  );
}
