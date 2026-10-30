import React from 'react';

export default function Avatar({ name = '', size = 'md' }) {
  const words = name.trim().split(/\s+/).filter(Boolean);
  const initials =
    [words[0], words.length > 1 && words.at(-1)]
      .filter(Boolean)
      .map((word) => Array.from(word)[0])
      .join('')
      .toUpperCase() || '?';
  const hue =
    Array.from(name).reduce((hash, character) => (hash * 31 + character.codePointAt(0)) >>> 0, 0) %
    360;
  return (
    <span
      className={`ui-avatar size-${size}`}
      role="img"
      aria-label={name || 'Unnamed account'}
      style={{ background: `hsl(${hue} 45% 88%)`, color: `hsl(${hue} 35% 22%)` }}
    >
      {initials}
    </span>
  );
}
