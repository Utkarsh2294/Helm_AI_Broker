import React, { useId } from 'react';

export default function PlanDecisionButton({ value, onChange, label = 'Plan review decision' }) {
  const name = useId();
  return (
    <fieldset className="ui-decisions">
      <legend className="sr-only">{label}</legend>
      {[
        ['YES', 'Recommend'],
        ['NO', 'Exclude'],
        ['REFER', 'Refer to UW'],
      ].map(([choice, text]) => (
        <label key={choice} className={value === choice ? `active ${choice.toLowerCase()}` : ''}>
          <input
            type="radio"
            name={name}
            value={choice}
            checked={value === choice}
            onChange={() => onChange(choice)}
          />
          {text}
        </label>
      ))}
    </fieldset>
  );
}
