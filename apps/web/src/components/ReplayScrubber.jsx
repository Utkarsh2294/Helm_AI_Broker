import React, { useRef, useState } from 'react';
import { api } from '../api';
export default function ReplayScrubber({ item, onView, onPresent }) {
  const [position, setPosition] = useState(null),
    [error, setError] = useState('');
  const request = useRef(0);
  const events = item.events || [];
  async function select(value) {
    setPosition(value);
    setError('');
    const order = ++request.current;
    if (value === events.length) {
      onPresent();
      return;
    }
    try {
      const data = await api(
        `/cases/${item.id}/replay?at=${encodeURIComponent(events[value].created_at)}`,
      );
      if (order === request.current) onView(data);
    } catch (e) {
      setError(e.message);
    }
  }
  return (
    <div className="replay-controls">
      <label>
        Case time-machine
        <input
          aria-label="Case time-machine"
          type="range"
          min="0"
          max={events.length}
          value={position ?? events.length}
          onChange={(e) => select(Number(e.target.value))}
        />
      </label>
      {position !== null && position < events.length && (
        <div className="notice warning">
          <div>
            <strong>Historical view · read only</strong>
            <p>{new Date(events[position].created_at).toLocaleString('en-GB')}</p>
            <button
              className="text-button"
              onClick={() => {
                setPosition(events.length);
                request.current++;
                onPresent();
              }}
            >
              Return to present
            </button>
          </div>
        </div>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </div>
  );
}
