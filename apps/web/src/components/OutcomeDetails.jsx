import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, money, label } from '../api';

export default function OutcomeDetails() {
  const [data, setData] = useState(null),
    [error, setError] = useState('');
  useEffect(() => {
    api('/insights/outcomes')
      .then(setData)
      .catch((cause) => setError(cause.message));
  }, []);
  if (!data)
    return <p role={error ? 'alert' : 'status'}>{error || 'Loading measured outcomes…'}</p>;
  return (
    <section className="surface demo-showcase" aria-labelledby="outcomes-title">
      <h2 id="outcomes-title">Outcomes over the last 30 days</h2>
      {data.sample_limited && (
        <p className="notice warning">
          This view reached its snapshot sample limit. Export a scoped report before using these
          results for governance.
        </p>
      )}
      <p>
        Average observed review time:{' '}
        {data.mean_review_seconds === null
          ? 'not yet measured'
          : `${Math.round(data.mean_review_seconds)} seconds`}
        . Saved plan assessments: {data.ratings.total}; edited reasons: {data.ratings.edited}.
      </p>
      <div className="table-scroll">
        <table>
          <caption>Latest saved star ratings</caption>
          <thead>
            <tr>
              <th scope="col">Stars</th>
              <th scope="col">Assessments</th>
              <th scope="col">Distribution</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(data.ratings.stars).map(([stars, count]) => (
              <tr key={stars}>
                <th scope="row">{stars} of 5</th>
                <td>{count}</td>
                <td>
                  <meter
                    min="0"
                    max={Math.max(data.ratings.total, 1)}
                    value={count}
                    aria-label={`${count} assessments with ${stars} stars`}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3>Ranking agreement with broker choices</h3>
      {data.ndcg_series.length ? (
        <div className="table-scroll">
          <table>
            <caption>Daily NDCG@3, measured from recorded selections</caption>
            <thead>
              <tr>
                <th scope="col">Day</th>
                <th scope="col">Cases</th>
                <th scope="col">NDCG@3</th>
              </tr>
            </thead>
            <tbody>
              {data.ndcg_series.map((row) => (
                <tr key={row.day}>
                  <th scope="row">{row.day}</th>
                  <td>{row.cases}</td>
                  <td>{row.ndcg3.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted">No recorded selections in this period.</p>
      )}
      <h3>Complaints awaiting human review</h3>
      {data.complaints.length ? (
        <ul>
          {data.complaints.map((row) => (
            <li key={row.id}>
              <Link to={`/case/${row.case_id}`}>Open complaint case</Link> ·{' '}
              <strong>{label(row.severity)}</strong> · {row.business_days_remaining} business-clock
              days remaining
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">No open complaints in your case scope.</p>
      )}
      <h3>Recorded premium tax</h3>
      <p>
        {money(data.bound_ipt_pence)} IPT across {data.bound_cases} confirmed fictional bindings.
      </p>
      <p className="muted">{data.ipt_basis}</p>
      <details>
        <summary>Fairness and drift review slices</summary>
        <p>{data.fairness_note}</p>
        {data.cohorts.length ? (
          <div className="table-scroll">
            <table>
              <caption>Descriptive cohort outcomes; small groups suppressed</caption>
              <thead>
                <tr>
                  <th scope="col">Dimension</th>
                  <th scope="col">Group</th>
                  <th scope="col">Cases</th>
                  <th scope="col">NDCG@3</th>
                </tr>
              </thead>
              <tbody>
                {data.cohorts.map((row) => (
                  <tr key={`${row.axis}-${row.segment}`}>
                    <th scope="row">{label(row.axis)}</th>
                    <td>{row.segment}</td>
                    <td>{row.cases}</td>
                    <td>
                      {row.suppressed ? 'Suppressed (fewer than 5 cases)' : row.ndcg3.toFixed(3)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="muted">Collect reviewed cases before assessing cohorts.</p>
        )}
      </details>
    </section>
  );
}
