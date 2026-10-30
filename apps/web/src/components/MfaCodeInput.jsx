import React, { useRef } from 'react';

export default function MfaCodeInput({ value = '', onChange, onComplete, disabled = false }) {
  const inputs = useRef([]);
  const digits = value.padEnd(6, ' ').slice(0, 6).split('');
  function update(index, text) {
    const incoming = text.replace(/\D/g, '').slice(0, 6);
    const next = [...digits];
    if (!incoming) next[index] = ' ';
    else
      incoming.split('').forEach((digit, offset) => {
        if (index + offset < 6) next[index + offset] = digit;
      });
    const joined = next.join('').trimEnd();
    onChange(joined);
    inputs.current[Math.min(5, index + Math.max(1, incoming.length))]?.focus();
    if (/^\d{6}$/.test(joined)) onComplete?.(joined);
  }
  return (
    <fieldset className="ui-mfa-code">
      <legend>Authenticator code</legend>
      <div>
        {digits.map((digit, index) => (
          <input
            key={index}
            ref={(element) => {
              inputs.current[index] = element;
            }}
            aria-label={`Digit ${index + 1} of 6`}
            data-autofocus={index === 0 ? 'true' : undefined}
            value={digit.trim()}
            disabled={disabled}
            inputMode="numeric"
            autoComplete={index === 0 ? 'one-time-code' : 'off'}
            maxLength={index === 0 ? 6 : 1}
            onChange={(event) => update(index, event.target.value)}
            onPaste={(event) => {
              event.preventDefault();
              update(index, event.clipboardData.getData('text'));
            }}
            onKeyDown={(event) => {
              if (event.key === 'Backspace' && !digit.trim() && index > 0) {
                event.preventDefault();
                const next = [...digits];
                next[index - 1] = ' ';
                onChange(next.join('').trimEnd());
                inputs.current[index - 1]?.focus();
              }
              if (event.key === 'ArrowLeft' && index > 0) {
                event.preventDefault();
                inputs.current[index - 1]?.focus();
              }
              if (event.key === 'ArrowRight' && index < 5) {
                event.preventDefault();
                inputs.current[index + 1]?.focus();
              }
            }}
          />
        ))}
      </div>
    </fieldset>
  );
}
