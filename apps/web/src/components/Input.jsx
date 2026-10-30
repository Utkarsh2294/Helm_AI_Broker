import React, { useId, useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';

export default function Input({ id, label, type = 'text', error, hint, className = '', ...props }) {
  const generated = useId(),
    fieldId = id || generated;
  const [visible, setVisible] = useState(false);
  const description =
    [hint && `${fieldId}-hint`, error && `${fieldId}-error`].filter(Boolean).join(' ') || undefined;
  return (
    <div className={`ui-field ${className}`}>
      <div className="floating-input">
        <input
          aria-label={label}
          {...props}
          id={fieldId}
          type={type === 'password' && visible ? 'text' : type}
          placeholder={props.placeholder || ' '}
          aria-invalid={Boolean(error)}
          aria-describedby={description}
        />
        <label htmlFor={fieldId}>{label}</label>
        {type === 'password' && (
          <button
            type="button"
            className="password-toggle"
            aria-label={visible ? 'Hide password' : 'Show password'}
            aria-pressed={visible}
            onClick={() => setVisible(!visible)}
          >
            {visible ? <EyeOff size={18} /> : <Eye size={18} />}
          </button>
        )}
      </div>
      {hint && (
        <small id={`${fieldId}-hint`} className="field-hint">
          {hint}
        </small>
      )}
      {error && (
        <small id={`${fieldId}-error`} className="field-error" role="alert">
          {error}
        </small>
      )}
    </div>
  );
}
