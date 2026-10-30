import React, { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { springFast, slideUp } from '../design/motion';
export default function AgentPill({ state, events }) {
  const [elapsed, setElapsed] = useState(0),
    [expanded, setExpanded] = useState(false);
  const active = ['INTAKE_RUNNING', 'QUOTES_PENDING', 'RANKING', 'SUITABILITY_DRAFT'].includes(
    state,
  );
  useEffect(() => {
    setElapsed(0);
    const timer = setInterval(() => setElapsed((v) => v + 1), 1000);
    return () => clearInterval(timer);
  }, [state]);
  return (
    <AnimatePresence>
      {active && (
        <motion.aside className="agent-pill" {...slideUp} transition={springFast}>
          <button onClick={() => setExpanded(!expanded)}>
            <span className="status-dot" />
            {state === 'QUOTES_PENDING'
              ? 'Agent 2 · Collecting quotations'
              : 'Agent · Working'} · {elapsed}s
          </button>
          {expanded && (
            <div>
              {events.slice(-5).map((e) => (
                <p key={e.seq}>{e.ui_message || e.type.replaceAll('_', ' ')}</p>
              ))}
            </div>
          )}
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
