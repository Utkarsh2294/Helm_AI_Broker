import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { springNormal } from '../design/motion';
import { api, label } from '../api';
export default function RankingTools({ item }) {
  const [planId, setPlanId] = useState(item.ranking.top[0]?.plan.id),
    [question, setQuestion] = useState(''),
    [answer, setAnswer] = useState(null),
    [error, setError] = useState('');
  const row = item.ranking.top.find((r) => r.plan.id === planId);
  async function ask(value) {
    setQuestion(value);
    setError('');
    try {
      setAnswer(
        await api(`/cases/${item.id}/ranking/copilot`, {
          method: 'POST',
          body: { question: value, ranking_id: item.ranking.id },
        }),
      );
    } catch (e) {
      setError(e.message);
    }
  }
  return (
    <section className="ranking-tools">
      <h3>Explore the score.</h3>
      <select
        aria-label="Score breakdown plan"
        value={planId}
        onChange={(e) => setPlanId(e.target.value)}
      >
        {item.ranking.top.map((r) => (
          <option key={r.plan.id} value={r.plan.id}>
            {r.plan.name}
          </option>
        ))}
      </select>
      {row && (
        <div className="weight-bars">
          {Object.entries(row.points).map(([criterion, points]) => (
            <div key={`${planId}:${criterion}`}>
              <span>{label(criterion)}</span>
              <div className="bar-track">
                <motion.div
                  style={{
                    width: `${(points / Math.max(...Object.values(row.points))) * 100}%`,
                    transformOrigin: 'left',
                  }}
                  initial={{ scaleX: 0 }}
                  animate={{ scaleX: 1 }}
                  transition={springNormal}
                />
              </div>
              <strong>{points.toFixed(1)}</strong>
            </div>
          ))}
        </div>
      )}
      <h3>Ask the ranking copilot.</h3>
      <p className="muted">Answers come directly from the saved score breakdown.</p>
      <div className="button-row">
        <button className="button small" onClick={() => ask('Why is #2 above #3?')}>
          Why #2 above #3?
        </button>
        <button className="button small" onClick={() => ask("What's driving #1's score?")}>
          What drives #1?
        </button>
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(question);
        }}
      >
        <input
          aria-label="Ranking question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about the ranking…"
        />
        <button className="button">Ask</button>
      </form>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {answer && (
        <div className="notice">
          <div>
            <p>{answer.answer}</p>
            <small>{answer.cited_fields.join(' · ')}</small>
          </div>
        </div>
      )}
    </section>
  );
}
