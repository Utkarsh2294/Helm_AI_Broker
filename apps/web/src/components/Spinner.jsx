import React from 'react';

export default function Spinner({ size = 'md', label = 'Loading', ...props }) {
  return (
    <svg
      className={`ui-spinner size-${size}`}
      viewBox="0 0 24 24"
      role="img"
      aria-label={label}
      {...props}
    >
      <circle
        cx="12"
        cy="12"
        r="9"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeDasharray="42 15"
      />
    </svg>
  );
}
