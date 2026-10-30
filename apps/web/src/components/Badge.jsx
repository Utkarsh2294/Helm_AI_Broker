import React from 'react';

export default function Badge({ label, variant = 'neutral', children }) {
  return <span className={`ui-badge ${variant}`}>{label || children}</span>;
}
