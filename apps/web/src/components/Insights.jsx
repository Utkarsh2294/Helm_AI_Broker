import React, { useEffect, useState } from 'react';
import { api } from '../api';
export default function Insights() {
  const [data, setData] = useState(null),
    [error, setError] = useState('');
  useEffect(() => {
    api('/insights')
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);
  if (error) return <p role="alert">{error}</p>;
  if (!data) return <p className="muted">Loading measured case insights…</p>;
  return (
    <section className="metrics-grid insights-metrics" aria-label="Case insights">
      {[
        [data.cases, 'Cases received'],
        [data.labelled_cases, 'Cases with feedback'],
        [
          data.satisfaction === null ? '—' : `${(data.satisfaction * 100).toFixed(0)}%`,
          'Survey satisfaction',
        ],
        [Object.values(data.halts).reduce((a, b) => a + b, 0), 'Agent halts'],
      ].map(([value, text]) => (
        <article className="surface metric-card" key={text}>
          <strong>{value}</strong>
          <p>{text}</p>
        </article>
      ))}
    </section>
  );
}
