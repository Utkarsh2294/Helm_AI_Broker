import { useEffect, useState } from 'react';
import { api } from '../api';
export default function useSSE(caseId, onEvent) {
  const [events, setEvents] = useState([]);
  useEffect(() => {
    if (!caseId) return;
    let source,
      timer,
      stopped = false,
      cursor = 0,
      delay = 1000;
    const seen = new Set();
    setEvents([]);
    function append(items) {
      const fresh = items.filter((event) => {
        if (seen.has(event.seq)) return false;
        seen.add(event.seq);
        cursor = Math.max(cursor, event.seq);
        return true;
      });
      if (fresh.length) {
        setEvents((previous) => [...previous, ...fresh]);
        onEvent?.(fresh.at(-1));
        const response = fresh.find(
          (event) =>
            event.type.startsWith('consumer.') && Date.now() - Date.parse(event.created_at) < 10000,
        );
        if (response && 'Notification' in window && Notification.permission === 'granted')
          new Notification('Helm: consumer update', {
            body: 'A consumer response is recorded. Open the case to review.',
            tag: `helm-${caseId}-${response.seq}`,
          });
      }
    }
    function connect() {
      if (stopped) return;
      source = new EventSource(`/api/v1/cases/${caseId}/stream?after=${cursor}`, {
        withCredentials: true,
      });
      source.onopen = () => {
        delay = 1000;
      };
      source.onmessage = (message) => {
        try {
          append([JSON.parse(message.data)]);
        } catch {
          source.close();
        }
      };
      source.onerror = () => {
        source.close();
        if (!stopped) timer = setTimeout(connect, delay);
        delay = Math.min(delay * 2, 30000);
      };
    }
    api(`/cases/${caseId}/events`)
      .then((items) => {
        if (!stopped) {
          append(items);
          connect();
        }
      })
      .catch(() => {
        timer = setTimeout(connect, delay);
      });
    return () => {
      stopped = true;
      source?.close();
      clearTimeout(timer);
    };
  }, [caseId]);
  return events;
}
