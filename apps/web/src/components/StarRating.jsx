import React, { useState } from 'react';
import { Star } from 'lucide-react';

export default function StarRating({
  value,
  onChange,
  readOnly = false,
  size = 'md',
  label = 'Plan suitability rating',
}) {
  const [preview, setPreview] = useState(null);
  const display = preview ?? value ?? 0;
  return (
    <div className={`ui-stars size-${size}`} onPointerLeave={() => setPreview(null)}>
      <span className="ui-star-icons" aria-hidden="true">
        {[1, 2, 3, 4, 5].map((star) => (
          <Star key={star} className={star <= display ? 'filled' : ''} />
        ))}
      </span>
      {readOnly ? (
        <span className="sr-only">
          {label}: {value || 'not rated'} of 5
        </span>
      ) : (
        <input
          type="range"
          min="1"
          max="5"
          step="1"
          value={value || 1}
          aria-label={label}
          aria-valuetext={value ? `${value} of 5 stars` : 'Not rated'}
          onChange={(event) => onChange(Number(event.target.value))}
          onPointerMove={(event) => {
            if (event.pointerType === 'mouse') {
              const box = event.currentTarget.getBoundingClientRect();
              setPreview(
                Math.max(1, Math.min(5, Math.ceil(((event.clientX - box.left) / box.width) * 5))),
              );
            }
          }}
          onKeyDown={(event) => {
            const next = {
              ArrowRight: Math.min(5, (value || 0) + 1),
              ArrowUp: Math.min(5, (value || 0) + 1),
              ArrowLeft: Math.max(1, (value || 1) - 1),
              ArrowDown: Math.max(1, (value || 1) - 1),
              Home: 1,
              End: 5,
              Enter: value || 1,
              ' ': value || 1,
            }[event.key];
            if (next !== undefined) {
              event.preventDefault();
              setPreview(null);
              onChange(next);
            }
          }}
        />
      )}
    </div>
  );
}
