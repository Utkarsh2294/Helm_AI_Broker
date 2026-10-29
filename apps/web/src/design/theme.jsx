import React, { useEffect, useState } from 'react';
import { Moon, Sun } from 'lucide-react';

export default function ThemeToggle() {
  const [theme, setTheme] = useState(() => localStorage.getItem('helm-theme') ||
    (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));
  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem('helm-theme', theme); }, [theme]);
  return <button className="icon-button" aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`} onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>{theme === 'dark' ? <Sun size={16}/> : <Moon size={16}/>}</button>;
}
