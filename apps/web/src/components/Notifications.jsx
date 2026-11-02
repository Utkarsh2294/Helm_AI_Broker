import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { Toaster, toast } from 'sonner';
import { Bell, Check, ArrowUpRight, X } from 'lucide-react';
import { api } from '../api';
import { useSessionStore } from '../session-store';
import { createPortal } from 'react-dom';
import usePanelHost from '../hooks/usePanelHost';

const Notifications = createContext(null);
export const useNotifications = () => useContext(Notifications);

export function NotificationProvider({ children }) {
  const user = useSessionStore((state) => state.user);
  const toasterHost = usePanelHost(Boolean(user));
  const queryClient = useQueryClient(),
    location = useLocation(),
    navigate = useNavigate();
  const path = useRef(location.pathname),
    batch = useRef([]),
    [connected, setConnected] = useState(false);
  path.current = location.pathname;
  const inbox = useQuery({
    queryKey: ['notifications', user?.id],
    queryFn: () => api('/notifications?actionable=true'),
    enabled: Boolean(user),
    refetchInterval: 30000,
  });
  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ['notifications'] }),
      queryClient.invalidateQueries({ queryKey: ['tasks'] }),
      queryClient.invalidateQueries({ queryKey: ['priority-summary'] }),
      queryClient.invalidateQueries({ queryKey: ['cases'] }),
    ]);
  async function openNotification(item) {
    await api(`/notifications/${item.id}/read`, { method: 'POST' });
    await refresh();
    navigate(item.href || `/case/${encodeURIComponent(item.case_id)}`);
  }
  useEffect(() => {
    if (!user) return;
    const source = new EventSource('/api/v1/notifications/stream');
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.onmessage = (event) => {
      const item = JSON.parse(event.data);
      refresh();
      if (!item.actionable || item.read_at) return;
      const activeCase = path.current.startsWith('/case/')
        ? decodeURIComponent(path.current.slice(6))
        : null;
      if (activeCase && activeCase !== item.case_id) return;
      const now = Date.now();
      batch.current = batch.current.filter((row) => now - row.at < 120000);
      const entry = { at: now, id: `notification-${item.id}` };
      batch.current.push(entry);
      if (batch.current.length > 3) {
        batch.current.forEach((row) => toast.dismiss(row.id));
        toast(`${batch.current.length} workspace updates`, {
          id: `notification-digest-${user.id}`,
          duration: 6000,
          action: { label: 'Open inbox', onClick: () => navigate('/notifications') },
        });
      } else {
        toast(
          <button
            className="notification-toast"
            onClick={() => {
              toast.dismiss(entry.id);
              openNotification(item).catch((error) => toast.error(error.message));
            }}
          >
            <strong>{item.title}</strong>
            <span>{item.message}</span>
            <small>
              Open case <ArrowUpRight size={14} />
            </small>
          </button>,
          { id: entry.id, duration: 6000 },
        );
      }
    };
    return () => {
      source.close();
      setConnected(false);
      batch.current = [];
      toast.dismiss();
    };
  }, [user?.id]);
  return (
    <Notifications.Provider value={{ inbox, refresh, connected, openNotification }}>
      {children}
      {createPortal(
        <Toaster
          theme="light"
          position="top-right"
          closeButton
          duration={6000}
          toastOptions={{ style: { fontFamily: 'inherit' } }}
        />,
        toasterHost || document.body,
      )}
    </Notifications.Provider>
  );
}

function NotificationRows({ items, open }) {
  return items.length ? (
    items.map((item) => (
      <button
        className={`notification-row ${item.read_at ? '' : 'unread'}`}
        key={item.id}
        onClick={() => open(item).catch((error) => toast.error(error.message))}
      >
        <span>
          <strong>{item.title}</strong>
          <small>{item.message}</small>
          {item.case_id && <small>Case {item.case_id.slice(0, 8)}</small>}
          <time dateTime={item.created_at}>
            {new Date(item.created_at).toLocaleString('en-GB')}
          </time>
        </span>
        {!item.read_at && <span aria-label="Unread" className="notification-dot" />}
      </button>
    ))
  ) : (
    <p className="muted">No notifications in this view.</p>
  );
}

export function NotificationBell() {
  const { inbox, refresh, connected, openNotification } = useNotifications();
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          className="button small notification-bell"
          aria-label={`Notifications, ${inbox.data?.unread || 0} unread`}
        >
          <Bell size={18} />
          {Boolean(inbox.data?.unread) && <span>{inbox.data.unread}</span>}
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content className="notification-menu" align="end" sideOffset={8}>
          <DropdownMenu.Label>Notifications</DropdownMenu.Label>
          <p className="muted">
            {connected ? 'Live updates connected' : 'Saved inbox · live feed reconnecting'}
          </p>
          <div className="notification-menu-list">
            {(inbox.data?.items || []).map((item) => (
              <DropdownMenu.Item
                key={item.id}
                onSelect={() => openNotification(item).catch((error) => toast.error(error.message))}
              >
                <strong>{item.title}</strong>
                <small>{item.message}</small>
                <time>{new Date(item.created_at).toLocaleTimeString('en-GB')}</time>
              </DropdownMenu.Item>
            ))}
          </div>
          <DropdownMenu.Item
            onSelect={() =>
              api('/notifications/read-all', { method: 'POST' })
                .then(refresh)
                .catch((error) => toast.error(error.message))
            }
          >
            Mark all read
          </DropdownMenu.Item>
          <DropdownMenu.Item asChild>
            <Link to="/notifications">
              Open full inbox and preferences <ArrowUpRight size={14} />
            </Link>
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

export function PriorityBanner() {
  const user = useSessionStore((state) => state.user),
    navigate = useNavigate();
  const { data } = useQuery({
    queryKey: ['priority-summary', user.id],
    queryFn: () => api('/dashboard/priority-summary'),
    refetchInterval: 60000,
  });
  const [dismissed, setDismissed] = useState('');
  const key = data ? `helm-priority-dismissed:${user.id}:${data.login_epoch}` : '';
  let hidden = dismissed === key;
  try {
    hidden ||= sessionStorage.getItem(key) === 'true';
  } catch {
    /* Optional browser state. */
  }
  useEffect(() => {
    if (!data?.voice_banner || hidden || !window.speechSynthesis) return;
    try {
      const spoken = `${key}:spoken`;
      if (sessionStorage.getItem(spoken)) return;
      const utterance = new SpeechSynthesisUtterance(
        `${data.action_needed} cases need your attention. ${data.overdue} are overdue and ${data.halted} are on hold.`,
      );
      utterance.lang = 'en-GB';
      window.speechSynthesis.speak(utterance);
      sessionStorage.setItem(spoken, 'true');
    } catch {
      /* Reading aloud is optional and browser-dependent. */
    }
  }, [data, key, hidden]);
  if (!data || hidden) return null;
  return (
    <section className="priority-banner" aria-label="Your login priorities">
      <div>
        <strong>
          {data.action_needed
            ? `${data.action_needed} cases need your attention`
            : 'You’re all caught up'}
        </strong>
        <p>
          {data.overdue} overdue · {data.new} new since your last login · {data.halted} on hold
        </p>
      </div>
      <button className="button small" onClick={() => navigate('/priority-queue')}>
        Review priority queue <ArrowUpRight size={15} />
      </button>
      <button
        className="icon-button"
        aria-label="Dismiss priority banner for this login"
        onClick={() => {
          setDismissed(key);
          try {
            sessionStorage.setItem(key, 'true');
          } catch {
            /* Optional state. */
          }
        }}
      >
        <X size={17} />
      </button>
    </section>
  );
}

export function NotificationInbox() {
  const user = useSessionStore((state) => state.user);
  const { refresh, openNotification } = useNotifications();
  const [actionable, setActionable] = useState(true),
    [cursor, setCursor] = useState('');
  const { data, error, isPending } = useQuery({
    queryKey: ['notifications', 'full', user.id, actionable, cursor],
    queryFn: () =>
      api(`/notifications?limit=50&actionable=${actionable}&cursor=${encodeURIComponent(cursor)}`),
  });
  const [zone, setZone] = useState(
      Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/London',
    ),
    [voice, setVoice] = useState(false);
  const preferences = useQuery({
    queryKey: ['notification-preferences', user.id],
    queryFn: () => api('/notifications/preferences'),
  });
  useEffect(() => {
    if (preferences.data) {
      setZone(preferences.data.timezone);
      setVoice(preferences.data.voice_banner);
    }
  }, [preferences.data]);
  return (
    <section className="notifications-page">
      <h1>Your notifications</h1>
      <p className="muted">Saved workspace updates, scoped to cases you can currently access.</p>
      <div className="assistant-toolbar">
        <label>
          <input
            type="checkbox"
            checked={actionable}
            onChange={(event) => {
              setActionable(event.target.checked);
              setCursor('');
            }}
          />
          Only actionable updates
        </label>
        <button
          className="button small"
          onClick={() =>
            api('/notifications/read-all', { method: 'POST' })
              .then(refresh)
              .catch((cause) => toast.error(cause.message))
          }
        >
          <Check size={15} />
          Mark all read
        </button>
      </div>
      {error && (
        <p role="alert" className="error">
          {error.message}
        </p>
      )}
      {isPending ? (
        <p role="status">Loading your saved inbox…</p>
      ) : (
        <NotificationRows items={data?.items || []} open={openNotification} />
      )}
      {data?.next_cursor && (
        <button className="button small" onClick={() => setCursor(data.next_cursor)}>
          Older updates
        </button>
      )}
      <section className="notification-preferences">
        <h2>Notification preferences</h2>
        <label htmlFor="notification-timezone">Daily digest timezone</label>
        <input
          id="notification-timezone"
          value={zone}
          onChange={(event) => setZone(event.target.value)}
        />
        <label>
          <input
            type="checkbox"
            checked={voice}
            onChange={(event) => setVoice(event.target.checked)}
          />
          Read my priority banner aloud when supported
        </label>
        <button
          className="button small"
          onClick={() =>
            api('/notifications/preferences', {
              method: 'PUT',
              body: { timezone: zone, voice_banner: voice },
            })
              .then(() => toast.success('Preferences saved'))
              .catch((cause) => toast.error(cause.message))
          }
        >
          Save preferences
        </button>
        <PushOptIn />
      </section>
    </section>
  );
}

function PushOptIn() {
  const [notice, setNotice] = useState(''),
    [busy, setBusy] = useState(false);
  async function enable() {
    setBusy(true);
    try {
      const capability = await api('/notifications/push/config');
      if (!capability.available) throw new Error(capability.notice);
      if (!('Notification' in window) || !('serviceWorker' in navigator))
        throw new Error('Browser push is not supported here. Your in-app inbox still works.');
      const permission = await Notification.requestPermission();
      if (permission !== 'granted')
        throw new Error('Browser notification permission was not granted.');
      const registration = await navigator.serviceWorker.register('/sw.js');
      const key = capability.public_key.replaceAll('-', '+').replaceAll('_', '/');
      const bytes = Uint8Array.from(atob(key + '='.repeat((4 - (key.length % 4)) % 4)), (char) =>
        char.charCodeAt(0),
      );
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: bytes,
      });
      await api('/notifications/push/subscribe', { method: 'POST', body: subscription.toJSON() });
      setNotice('Browser notifications enabled for this device.');
    } catch (cause) {
      setNotice(cause.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <button className="button small" disabled={busy} onClick={enable}>
        Enable browser notifications
      </button>
      {notice && <p role="status">{notice}</p>}
      <p className="muted">
        Optional. Permission is requested only after you click. Alerts contain a generic workspace
        reminder; sign in to see case details.
      </p>
    </div>
  );
}
