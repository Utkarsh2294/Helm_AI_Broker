import React, { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Download, MessageSquare } from 'lucide-react';
import { api } from '../api';
import AssistantCitations from './AssistantCitations';
import { useSessionStore } from '../session-store';

const number = (value, digits = 0) =>
  value == null
    ? 'Not recorded'
    : Number(value).toLocaleString('en-GB', { maximumFractionDigits: digits });
function Table({ columns, rows, caption }) {
  return rows.length ? (
    <div className="insight-table" tabIndex={0} role="region" aria-label={caption}>
      <table>
        <caption>{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {row.map((cell, j) => (
                <td key={j}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <p className="muted">No recorded observations in this view.</p>
  );
}
function LineChart({ rows, fields, label, reference, maxValue }) {
  if (!rows.length) return <p className="muted">No recorded observations to plot yet.</p>;
  const max =
    maxValue || Math.max(1, ...rows.flatMap((row) => fields.map((key) => Number(row[key]) || 0)));
  const point = (row, i, key) =>
    `${20 + (i * 640) / Math.max(1, rows.length - 1)},${180 - ((Number(row[key]) || 0) / max) * 150}`;
  return (
    <svg className="insight-chart" viewBox="0 0 680 200" role="img" aria-label={label}>
      <title>{label}</title>
      {reference && (
        <>
          <rect
            x="20"
            y={180 - (Number(reference) / max) * 150 - 5}
            width="640"
            height="10"
            fill="var(--amber)"
            opacity=".3"
          />
          <text x="20" y="16">
            Your reference {reference} (unverified)
          </text>
        </>
      )}
      {fields.map((key, index) => (
        <g key={key}>
          {fields.length > 1 && (
            <polygon
              points={`20,180 ${rows.map((row, i) => point(row, i, key)).join(' ')} 660,180`}
              fill={index ? 'var(--forest)' : 'var(--sage)'}
              opacity=".25"
            />
          )}
          <polyline
            points={rows.map((row, i) => point(row, i, key)).join(' ')}
            fill="none"
            stroke={index ? 'var(--sage)' : 'var(--forest)'}
            strokeWidth="3"
          />
          {rows.map((row, i) => (
            <circle
              key={i}
              cx={20 + (i * 640) / Math.max(1, rows.length - 1)}
              cy={180 - ((Number(row[key]) || 0) / max) * 150}
              r="4"
              fill="var(--forest)"
            >
              <title>
                {row.bucket || row.month || row.day}: {key} {number(row[key], 2)}
              </title>
            </circle>
          ))}
        </g>
      ))}
    </svg>
  );
}
function Sparkline({ values }) {
  const present = values.filter((value) => value != null);
  if (!present.length) return null;
  const max = Math.max(1, ...present.map(Number));
  return (
    <svg viewBox="0 0 100 30" className="insight-sparkline" aria-hidden="true">
      <polyline
        points={present
          .map(
            (value, i) =>
              `${(i * 100) / Math.max(1, present.length - 1)},${28 - (Number(value) * 26) / max}`,
          )
          .join(' ')}
        stroke="var(--forest)"
        strokeWidth="2"
        fill="none"
      />
    </svg>
  );
}
function Section({ title, children }) {
  return (
    <section className="insight-section">
      <h2>{title}</h2>
      {children}
    </section>
  );
}

export default function BrokerInsights() {
  const user = useSessionStore((state) => state.user),
    [params, setParams] = useSearchParams();
  const privileged = ['senior_broker', 'admin'].includes(user.role) || user.is_lead_broker,
    query = params.toString();
  const [summary, setSummary] = useState(null),
    [busy, setBusy] = useState(false),
    [failure, setFailure] = useState(''),
    [sort, setSort] = useState('selected');
  const { data, error, isPending, refetch } = useQuery({
    queryKey: ['broker-insights', user.id, user.role, user.is_lead_broker, query],
    queryFn: () => api(`/insights/dashboard?${query}`),
  });
  const brokers = useQuery({
    queryKey: ['insight-brokers', user.id],
    queryFn: () => api('/insights/brokers'),
    enabled: privileged,
  });
  function update(key, value) {
    setSummary(null);
    setParams((old) => {
      const next = new URLSearchParams(old);
      value ? next.set(key, value) : next.delete(key);
      return next;
    });
  }
  async function exportScorecard(format) {
    try {
      const blob = await api(`/insights/scorecard?${query}&format=${format}`, {
          responseType: 'blob',
        }),
        url = URL.createObjectURL(blob),
        link = document.createElement('a');
      link.href = url;
      link.download = `helm-scorecard.${format}`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (cause) {
      setFailure(cause.message);
    }
  }
  async function summarise() {
    setBusy(true);
    try {
      setSummary(
        await api('/insights/summary', {
          method: 'POST',
          body: {
            from_date: params.get('from') || null,
            to_date: params.get('to') || null,
            coverage_type: params.get('coverage_type') || null,
            broker_id: params.get('broker_id') || null,
            insurer_id: params.get('insurer_id') || null,
          },
        }),
      );
    } catch (cause) {
      setFailure(cause.message);
    } finally {
      setBusy(false);
    }
  }
  const insurers = [...(data?.insurers.rows || [])].sort((a, b) => (b[sort] || 0) - (a[sort] || 0));
  const reference =
    Number(params.get('benchmark')) >= 1 && Number(params.get('benchmark')) <= 5
      ? params.get('benchmark')
      : null;
  return (
    <section className="broker-insights">
      <div className="page-heading">
        <div>
          <span className="eyebrow">YOUR PRACTICE, IN VIEW</span>
          <h1>Broker insights</h1>
          <p className="muted">
            Saved operational observations. UTC intake-date cohorts; no clinical data or invented
            outcomes.
          </p>
        </div>
        <button className="button small" onClick={() => refetch()}>
          Refresh
        </button>
      </div>
      <div className="insights-filters">
        <label>
          From
          <input
            type="date"
            aria-label="Insights from date"
            value={params.get('from') || ''}
            onChange={(event) => update('from', event.target.value)}
          />
        </label>
        <label>
          To
          <input
            type="date"
            aria-label="Insights to date"
            value={params.get('to') || ''}
            onChange={(event) => update('to', event.target.value)}
          />
        </label>
        <label>
          Coverage
          <select
            value={params.get('coverage_type') || ''}
            onChange={(event) => update('coverage_type', event.target.value)}
          >
            <option value="">All cover types</option>
            {['individual', 'couple', 'family'].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        {privileged && (
          <label>
            Broker scope
            <select
              value={params.get('broker_id') || ''}
              onChange={(event) => update('broker_id', event.target.value)}
            >
              <option value="">My cases and unassigned</option>
              <option value="all">All brokers (senior access)</option>
              {brokers.data?.map((broker) => (
                <option value={broker.id} key={broker.id}>
                  {broker.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          Selected insurer
          <select
            value={params.get('insurer_id') || ''}
            onChange={(event) => update('insurer_id', event.target.value)}
          >
            <option value="">All insurers</option>
            {insurers.map((row) => (
              <option key={row.insurer_id}>{row.insurer_id}</option>
            ))}
          </select>
        </label>
      </div>
      {(error || failure) && (
        <p className="error" role="alert">
          {failure || error.message}
        </p>
      )}
      {isPending && <p role="status">Loading filtered saved observations…</p>}
      {data && (
        <>
          <div className="insight-kpis">
            {[
              ['Open in cohort', 'open', 'open'],
              ['Days to delivery/close', 'average_days_to_close', 'average_days'],
              ['Consumer satisfaction /5', 'csat', 'csat'],
              ['Past demo action SLA', 'past_action_sla', 'overdue'],
            ].map(([label, key, trend]) => (
              <article key={key}>
                <span>{label}</span>
                <strong>{number(data.overview[key], 2)}</strong>
                <Sparkline values={data.trend.map((row) => row[trend])} />
                <small>
                  {data.overview[key] != null && data.previous[key] != null
                    ? `${number(Number(data.overview[key]) - Number(data.previous[key]), 2)} change vs previous period`
                    : 'No previous observation for comparison'}
                </small>
              </article>
            ))}
          </div>
          <div className="insights-grid">
            <Section title="Intake volume">
              <label>
                Granularity
                <select
                  aria-label="Volume granularity"
                  value={params.get('granularity') || 'day'}
                  onChange={(event) => update('granularity', event.target.value)}
                >
                  {['day', 'week', 'month', 'year'].map((value) => (
                    <option key={value}>{value}</option>
                  ))}
                </select>
              </label>
              <LineChart
                rows={data.volume.rows}
                fields={['new', 'closed']}
                label="Intake totals and delivered/closed subset"
              />
              <details>
                <summary>View volume source values</summary>
                <Table
                  columns={['Period', 'New', 'Delivered/closed']}
                  rows={data.volume.rows.map((row) => [
                    String(row.bucket).slice(0, 10),
                    number(row.new),
                    number(row.closed),
                  ])}
                  caption="Volume source"
                />
              </details>
              <small>{data.volume.basis}</small>
            </Section>
            <Section title="Open case age">
              <div
                className="insight-bars"
                role="group"
                aria-label="Age buckets, click to filter queue"
              >
                {data.aging.buckets.map((row) => (
                  <Link
                    className="insight-bar"
                    key={row.key}
                    to={`/queue?age_range=${encodeURIComponent(row.key)}&sort=priority`}
                  >
                    <strong>{number(row.count)}</strong>
                    <span className="insight-bar-track">
                      <span
                        style={{
                          height: `${Math.max(1, (100 * row.count) / Math.max(1, ...data.aging.buckets.map((bucket) => bucket.count)))}%`,
                        }}
                      />
                    </span>
                    <span>{row.label}</span>
                  </Link>
                ))}
              </div>
              <small>{data.aging.basis}</small>
            </Section>
            <Section title="Consumer satisfaction">
              <label>
                Optional reference /5
                <input
                  type="number"
                  min="1"
                  max="5"
                  step="0.1"
                  aria-label="Custom satisfaction reference"
                  value={params.get('benchmark') || ''}
                  onChange={(event) => update('benchmark', event.target.value)}
                />
              </label>
              <LineChart
                rows={data.satisfaction.trend}
                fields={['score']}
                maxValue={5}
                reference={reference}
                label="Verified consumer satisfaction, scale one to five"
              />
              <Table
                columns={['Intake month', 'Score /5', 'Samples']}
                rows={data.satisfaction.trend.map((row) => [
                  row.month,
                  number(row.score, 2),
                  row.samples,
                ])}
                caption="Consumer satisfaction source"
              />
              <small>{data.satisfaction.notice}</small>
            </Section>
            <Section title="Time in saved stages">
              <Table
                columns={['Stage', 'Average days', 'Median days', 'Samples']}
                rows={data.timing.state_durations.map((row) => [
                  row.state.replaceAll('_', ' '),
                  number(row.average_days, 3),
                  number(row.median_days, 3),
                  row.samples,
                ])}
                caption="Completed state timings"
              />
              <p>Overall median to delivery/closure: {number(data.timing.median_days, 2)} days</p>
              <small>{data.timing.basis}</small>
            </Section>
          </div>
          <Section title="Insurer choice funnel">
            <label>
              Sort insurers
              <select value={sort} onChange={(event) => setSort(event.target.value)}>
                <option value="selected">Selected</option>
                <option value="top_three">Top three</option>
                <option value="accepted">Accepted</option>
                <option value="quoted_turnaround_days">Quoted turnaround</option>
              </select>
            </label>
            <Table
              columns={[
                'Insurer',
                'Shown',
                'Rated 4–5',
                'Top three',
                'Selected',
                'Accepted',
                'Quoted days',
                'Saved upheld rate',
              ]}
              rows={insurers.map((row) => [
                row.insurer_id,
                row.shown,
                row.rated_highly,
                row.top_three,
                row.selected,
                row.accepted,
                number(row.quoted_turnaround_days, 1),
                number(row.saved_upheld_rate, 3),
              ])}
              caption="Saved insurer observations and choice funnel"
            />
            <small>{data.insurers.notice}</small>
          </Section>
          <div className="insights-grid">
            <Section title="Client preference patterns">
              <Table
                columns={['Requested coverage', 'Cases']}
                rows={data.patterns.coverage.map((row) => [row.label, row.count])}
                caption="Requested benefit tiers"
              />
              <Table
                columns={['Must-have', 'Cases']}
                rows={data.patterns.must_have.map((row) => [row.label, row.count])}
                caption="Must-have requests"
              />
              <Table
                columns={['Underwriting', 'Cases']}
                rows={data.patterns.underwriting.map((row) => [row.label, row.count])}
                caption="Underwriting preferences"
              />
              {['open', 'closed'].map((key) => (
                <p key={key}>
                  {key === 'open' ? 'Open' : 'Delivered/closed'} median budget:{' '}
                  {data.patterns.budget[key].median_pence == null
                    ? 'Not recorded'
                    : `£${number(data.patterns.budget[key].median_pence / 100, 2)}`}
                </p>
              ))}
              <small>{data.patterns.notice}</small>
            </Section>
            <Section title="Retention and satisfaction signals">
              <p>{data.cohorts.notice}</p>
              <p>
                Identified consumers: {data.cohorts.identified_consumers}; repeated intakes:{' '}
                {data.cohorts.repeat_intakes}
              </p>
              <p>
                Confirmed renewal retention:{' '}
                {data.cohorts.renewal_rate == null
                  ? 'Not recorded'
                  : `${number(data.cohorts.renewal_rate * 100, 1)}%`}{' '}
                · {data.cohorts.confirmed_renewals || 0} confirmed renewals /{' '}
                {data.cohorts.eligible_renewal_cases || 0} eligible source cases.
              </p>
              <p>{data.drivers.notice || data.drivers.status}</p>
              {data.drivers.drivers && (
                <Table
                  columns={['Factor', 'Standardised coefficient']}
                  rows={data.drivers.drivers.map((row) => [
                    row.feature,
                    number(row.standardised_coefficient, 3),
                  ])}
                  caption="Descriptive satisfaction associations"
                />
              )}
              <h3>Unusual stage age</h3>
              {data.anomalies.items.length ? (
                data.anomalies.items.map((item) => (
                  <p key={item.case_id}>
                    <Link to={item.href}>Case {item.case_id.slice(0, 8)}</Link> ·{' '}
                    {number(item.days_in_state, 2)} days in {item.state.replaceAll('_', ' ')};
                    historical median {number(item.median_days, 2)} days.
                  </p>
                ))
              ) : (
                <p>No supported aging anomalies in this view.</p>
              )}
              <small>{data.anomalies.notice}</small>
            </Section>
          </div>
          {data.productivity && (
            <Section title="Senior broker operational context">
              <Table
                columns={['Broker ID', 'Cases', 'Average days to delivery/close']}
                rows={data.productivity.rows.map((row) => [
                  row.broker_id || 'Unassigned',
                  row.cases,
                  number(row.average_days_to_close, 2),
                ])}
                caption="Broker cohort volumes (restricted)"
              />
              <p>
                Anonymised team median: {number(data.productivity.anonymous_team_median_days, 2)}{' '}
                days
              </p>
              <small>{data.productivity.notice}</small>
            </Section>
          )}
          <Section title="Oldest open cases">
            <Table
              columns={['Case', 'State', 'Received']}
              rows={data.aging.oldest.map((row) => [
                <Link key={row.case_id} to={`/case/${row.case_id}`}>
                  {row.case_id.slice(0, 8)}
                </Link>,
                row.state.replaceAll('_', ' '),
                new Date(row.created_at).toLocaleDateString('en-GB'),
              ])}
              caption="Oldest open cases in this intake cohort"
            />
          </Section>
          <div className="assistant-toolbar">
            <button className="button small" onClick={() => exportScorecard('pdf')}>
              <Download size={15} />
              PDF scorecard
            </button>
            <button className="button small" onClick={() => exportScorecard('csv')}>
              <Download size={15} />
              CSV scorecard
            </button>
            <button className="button primary" disabled={busy} onClick={summarise}>
              <MessageSquare size={15} />
              {busy ? 'Reading saved aggregates…' : 'Summarise my period'}
            </button>
          </div>
          {summary && (
            <section className="assistant-message">
              <h2>Saved-record period summary</h2>
              <AssistantCitations text={summary.answer} sources={summary.sources} />
              <small>
                {summary.confidence} · {summary.model_version} ·{' '}
                {new Date(summary.timestamp).toLocaleString('en-GB')}
              </small>
              <details>
                <summary>Sources</summary>
                {summary.sources.map((source, index) => (
                  <p key={index}>
                    [{index + 1}] {source.label}
                  </p>
                ))}
              </details>
            </section>
          )}
        </>
      )}
    </section>
  );
}
