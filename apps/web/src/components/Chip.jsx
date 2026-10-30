import React from 'react';
import { X } from 'lucide-react';

export default function Chip({ label, icon, onRemove }) {
  return (
    <span className="ui-chip">
      {icon}
      {label}
      {onRemove && (
        <button type="button" aria-label={`Remove ${label}`} onClick={onRemove}>
          <X size={12} />
        </button>
      )}
    </span>
  );
}
