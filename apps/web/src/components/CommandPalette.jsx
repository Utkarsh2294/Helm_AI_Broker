import React, { useEffect, useMemo, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import Fuse from 'fuse.js';
import { Search } from 'lucide-react';
import { api } from '../api';
export default function CommandPalette({ cases, onCase, onPage }) {
  const [open, setOpen] = useState(false), [query, setQuery] = useState(''), [selected, setSelected] = useState(0);
  const [remoteCases, setRemoteCases] = useState([]);
  useEffect(() => { let active = true; if (!query.trim()) { setRemoteCases([]); return; } const timer = setTimeout(() => api(`/cases?limit=20&q=${encodeURIComponent(query)}`).then(result => active && setRemoteCases(result.items)).catch(() => active && setRemoteCases([])), 180); return () => { active = false; clearTimeout(timer); }; }, [query]);
  useEffect(() => { const handle = event => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setOpen(v => !v); } }; window.addEventListener('keydown', handle); return () => window.removeEventListener('keydown', handle); }, []);
  const items = useMemo(() => [...new Map([...cases, ...remoteCases].map(c => [c.id, { key: c.id, label: `${c.name} · ${c.state}`, kind: 'Case' }])).values(), ...[['security', 'Security & devices'], ['audit', 'Activity & audit'], ['learning', 'Learning & insights']].map(([key, name]) => ({ key, label: name, kind: 'Page' }))], [cases, remoteCases]);
  const found = query ? new Fuse(items, { keys: ['label', 'key'], threshold: 0.4 }).search(query).map(r => r.item) : items.slice(0, 8);
  function choose(item) { if (!item) return; item.kind === 'Case' ? onCase(item.key) : onPage(item.key); setOpen(false); setQuery(''); }
  return <Dialog.Root open={open} onOpenChange={setOpen}><Dialog.Trigger asChild><button className="button small command-trigger"><Search size={14}/>Search <kbd>Ctrl K</kbd></button></Dialog.Trigger><Dialog.Portal><Dialog.Overlay className="command-overlay"/><Dialog.Content className="command-dialog" onKeyDown={e => { if (['ArrowDown', 'ArrowUp'].includes(e.key)) { e.preventDefault(); setSelected(v => (v + (e.key === 'ArrowDown' ? 1 : -1) + found.length) % Math.max(1, found.length)); } if (e.key === 'Enter') { e.preventDefault(); choose(found[selected]); } }}><Dialog.Title>Search your workspace</Dialog.Title><Dialog.Description className="muted">Cases, actions and account settings.</Dialog.Description><input autoFocus aria-label="Command search" placeholder="Search cases and actions…" value={query} onChange={e => { setQuery(e.target.value); setSelected(0); }}/><div role="listbox" aria-label="Search results">{found.map((item, i) => <button role="option" aria-selected={i === selected} className={i === selected ? 'active' : ''} key={item.key} onMouseEnter={() => setSelected(i)} onClick={() => choose(item)}><span>{item.label}</span><small>{item.kind}</small></button>)}</div><Dialog.Close className="button small">Close</Dialog.Close></Dialog.Content></Dialog.Portal></Dialog.Root>;
}
