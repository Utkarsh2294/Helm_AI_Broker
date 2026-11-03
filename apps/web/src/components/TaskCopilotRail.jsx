import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useLocation, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useDrag } from '@use-gesture/react';
import { motion, useMotionValue, useMotionTemplate, useReducedMotion } from 'framer-motion';
import { ArrowUpRight, Clock3, ListTodo, X } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '../api';
import { caseIdFromPath } from '../case-route';
import { useSessionStore } from '../session-store';
import keepPanelFocus from '../hooks/keepPanelFocus';
import AssistantCitations from './AssistantCitations';
import { useNotifications } from './Notifications';
import usePanelHost from '../hooks/usePanelHost';

function TaskCard({ task, onSnooze, onExplain, onOpen }) {
  const x = useMotionValue(0),
    transform = useMotionTemplate`translateX(${x}px)`,
    reduced = useReducedMotion();
  const bind = useDrag(
    ({ movement: [distance], last }) => {
      if (!reduced) x.set(Math.max(0, distance));
      if (last) {
        x.set(0);
        if (distance > 100) onSnooze(task, 'later');
      }
    },
    { axis: 'x', filterTaps: true },
  );
  const [reason, setReason] = useState('later');
  return (
    <motion.article className={`task-card ${task.overdue ? 'overdue' : ''}`} style={{ transform }}>
      <div {...bind()} className="task-card-grip">
        <small>
          {task.client} · {task.case_id.slice(0, 8)}
        </small>
        <h3>{task.title}</h3>
      </div>
      {task.task_key === 'rate_plans' && (
        <p>
          {task.rated} of {task.total} plans rated
        </p>
      )}
      {task.halt_code && <p>Recorded hold: {task.halt_code.replaceAll('_', ' ')}</p>}
      <p className="muted">
        {task.elapsed_days} days since broker action ·{' '}
        {task.overdue ? 'Past demo SLA' : 'Within demo SLA'}
      </p>
      <div className="assistant-toolbar">
        <button className="button small primary" onClick={() => onOpen(task.href)}>
          Open task <ArrowUpRight size={14} />
        </button>
        <button className="button small" onClick={() => onExplain(task)}>
          Why this matters
        </button>
      </div>
      <label>
        Remind me later
        <select
          aria-label={`Snooze reason for ${task.client}`}
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        >
          <option value="later">Later</option>
          <option value="waiting_on_consumer">Waiting on consumer</option>
          <option value="waiting_on_insurer_docs">Waiting on insurer documents</option>
        </select>
      </label>
      <button className="text-button" onClick={() => onSnooze(task, reason)}>
        <Clock3 size={14} />
        Snooze for one hour
      </button>
    </motion.article>
  );
}
const cardTypes = Object.fromEntries(
  [
    'select_policies',
    'rate_plans',
    'review_facts',
    'release_quotes',
    'final_signoff',
    'resolve_halt',
    'resolve_complaint',
    'resolve_referral',
    'missing_information',
  ].map((name) => [name, TaskCard]),
);

export default function TaskCopilotRail() {
  const user = useSessionStore((state) => state.user),
    { refresh } = useNotifications(),
    navigate = useNavigate(),
    location = useLocation();
  const [open, setOpen] = useState(false),
    [onlyCase, setOnlyCase] = useState(false),
    [explanation, setExplanation] = useState(null),
    [busy, setBusy] = useState(false),
    [instant, setInstant] = useState(false);
  const trigger = useRef(null),
    host = usePanelHost(true),
    reduced = useReducedMotion();
  const caseId = caseIdFromPath(location.pathname);
  const { data, error, refetch } = useQuery({
    queryKey: ['tasks', user.id, onlyCase ? caseId : null],
    queryFn: () =>
      api(`/tasks/rail${onlyCase && caseId ? `?case_id=${encodeURIComponent(caseId)}` : ''}`),
    refetchInterval: open ? 5000 : 30000,
  });
  useEffect(() => {
    if (open) refetch();
  }, [open, caseId, refetch]);
  const wasOpen = useRef(false),
    closeButton = useRef(null);
  useEffect(() => {
    if (open && instant) closeButton.current?.focus();
    else if (wasOpen.current && !open) trigger.current?.focus();
    wasOpen.current = open;
  }, [open, instant]);
  useEffect(() => {
    const close = () => setOpen(false);
    window.addEventListener('helm:assistant-open', close);
    return () => window.removeEventListener('helm:assistant-open', close);
  }, []);
  useEffect(() => {
    if (!open) return;
    function escape(event) {
      if (
        event.key === 'Escape' &&
        !document.querySelector('[data-helm-popover][data-state="open"]')
      ) {
        event.preventDefault();
        event.stopPropagation();
        setOpen(false);
        trigger.current?.focus();
      }
    }
    document.addEventListener('keydown', escape, true);
    return () => document.removeEventListener('keydown', escape, true);
  }, [open]);
  async function snooze(task, reason) {
    try {
      await api(`/tasks/${task.case_id}/${task.task_key}/snooze`, {
        method: 'POST',
        body: { reason },
      });
      await refresh();
      toast.success('Task snoozed for one hour. The case remains outstanding.');
    } catch (cause) {
      toast.error(cause.message);
    }
  }
  async function explain(task) {
    setBusy(true);
    setExplanation(null);
    try {
      setExplanation(
        await api('/assistant/explain-task', {
          method: 'POST',
          body: { case_id: task.case_id, task_key: task.task_key },
        }),
      );
    } catch (cause) {
      toast.error(cause.message);
    } finally {
      setBusy(false);
    }
  }
  if (!host) return null;
  const items = (data?.items || []).filter((task) => !onlyCase || task.case_id === caseId);
  return createPortal(
    <>
      {!open && (
        <button
          ref={trigger}
          className="task-rail-trigger button small"
          aria-expanded={open}
          onClick={(event) => {
            setInstant(event.detail === 0);
            window.dispatchEvent(new CustomEvent('helm:tasks-open'));
            setOpen(true);
          }}
        >
          <ListTodo size={17} />
          Tasks {data?.items?.length || 0}
        </button>
      )}
      {open && (
        <motion.aside
          className="task-copilot-rail"
          aria-label="Task copilot"
          onKeyDown={keepPanelFocus}
          initial={reduced || instant ? false : { opacity: 0, transform: 'translateX(100%)' }}
          animate={{ opacity: 1, transform: 'translateX(0%)' }}
          transition={{ type: 'spring', stiffness: 380, damping: 30 }}
        >
          <div className="section-header">
            <h2>Your next steps</h2>
            <button
              className="icon-button"
              aria-label="Close task copilot"
              ref={closeButton}
              onClick={() => {
                setOpen(false);
                trigger.current?.focus();
              }}
            >
              <X size={18} />
            </button>
          </div>
          <p className="muted">
            Saved case tasks, ordered by a reproducible priority score. Snoozing never resolves a
            case.
          </p>
          {caseId && (
            <label>
              <input
                type="checkbox"
                checked={onlyCase}
                onChange={(event) => setOnlyCase(event.target.checked)}
              />
              Only this case
            </label>
          )}
          {error && (
            <p className="error" role="alert">
              {error.message}
            </p>
          )}
          {busy && <p role="status">Reading the saved task context…</p>}
          {explanation && (
            <section className="task-explanation" aria-label="Why this task matters">
              <h3>Why this matters</h3>
              <AssistantCitations
                text={explanation.answer}
                sources={explanation.sources}
                caseId={caseId}
              />
              {explanation.sources.map((source, i) => (
                <p key={i}>
                  <small>
                    [{i + 1}] {source.label}
                  </small>
                </p>
              ))}
              <small>
                {explanation.model_version} ·{' '}
                {new Date(explanation.timestamp).toLocaleString('en-GB')}
              </small>
              <button className="text-button" onClick={() => setExplanation(null)}>
                Close explanation
              </button>
            </section>
          )}
          {items.length ? (
            items.map((task) => {
              const Card = cardTypes[task.type] || TaskCard;
              return (
                <Card
                  key={`${task.case_id}:${task.task_key}`}
                  task={task}
                  onSnooze={snooze}
                  onExplain={explain}
                  onOpen={(href) => {
                    setOpen(false);
                    navigate(href);
                  }}
                />
              );
            })
          ) : (
            <p>You’re all caught up. No unsnoozed broker actions are recorded in this view.</p>
          )}
          <small className="muted">{data?.priority_basis}</small>
        </motion.aside>
      )}
    </>,
    host,
  );
}
