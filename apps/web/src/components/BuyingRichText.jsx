import React, { useId, useRef } from 'react';

export function RichText({ value }) {
  return value
    .split('\n')
    .map((line, index) => (
      <p key={index}>
        {line
          .split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g)
          .map((part, position) =>
            part.startsWith('**') && part.endsWith('**') ? (
              <strong key={position}>{part.slice(2, -2)}</strong>
            ) : part.startsWith('*') && part.endsWith('*') ? (
              <em key={position}>{part.slice(1, -1)}</em>
            ) : (
              part
            ),
          )}
      </p>
    ));
}

export default function BuyingRichText({ label, value, onChange }) {
  const id = useId(),
    input = useRef(null);
  function format(marker) {
    const start = input.current.selectionStart,
      end = input.current.selectionEnd;
    const selected = value.slice(start, end) || 'text';
    const next = value.slice(0, start) + marker + selected + marker + value.slice(end);
    if (next.length <= 2000) {
      onChange(next);
      requestAnimationFrame(() => {
        input.current?.focus();
        input.current?.setSelectionRange(
          start + marker.length,
          start + marker.length + selected.length,
        );
      });
    }
  }
  return (
    <div className="pb-edit-block">
      <label htmlFor={id}>{label}</label>
      <div role="group" aria-label={`Format ${label}`}>
        <button className="button small" type="button" onClick={() => format('**')}>
          Bold
        </button>
        <button className="button small" type="button" onClick={() => format('*')}>
          Italic
        </button>
      </div>
      <textarea
        id={id}
        ref={input}
        value={value}
        required
        maxLength={2000}
        onChange={(event) => onChange(event.target.value)}
      />
      <details>
        <summary>Formatted preview</summary>
        <RichText value={value} />
      </details>
    </div>
  );
}
