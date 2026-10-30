import React, { useId, useState } from 'react';

export default function TextArea({
  label,
  value = '',
  onChange,
  onBlur,
  minLength,
  hint,
  id,
  ...props
}) {
  const generated = useId(),
    fieldId = id || generated;
  const [touched, setTouched] = useState(false);
  const short = touched && minLength && value.trim().length < minLength;
  return (
    <div className="ui-field">
      <label htmlFor={fieldId}>{label}</label>
      <textarea
        {...props}
        id={fieldId}
        value={value}
        onChange={onChange}
        minLength={minLength}
        onBlur={(event) => {
          setTouched(true);
          onBlur?.(event);
        }}
        aria-invalid={Boolean(short)}
        aria-describedby={`${fieldId}-hint`}
      />
      <small id={`${fieldId}-hint`} className={short ? 'field-error' : 'field-hint'}>
        {short ? `Minimum ${minLength} characters required. ` : hint}
        {minLength ? ` ${value.trim().length}/${minLength} characters` : ''}
      </small>
    </div>
  );
}
