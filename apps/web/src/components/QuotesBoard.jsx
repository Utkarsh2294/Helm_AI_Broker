import React, { useEffect, useState } from 'react';
import { api, label } from '../api';
export default function QuotesBoard({ item }) {
  const [partners, setPartners] = useState([]), [now, setNow] = useState(Date.now());
  useEffect(() => { api('/partners').then(setPartners).catch(() => {}); const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
  const remaining = Math.max(0, Math.round((new Date(item.rfq?.deadline).getTime() - now) / 1000));
  const simulated = remaining * 2700;
  return <section className="quotes-board"><div className="section-header"><h3>Partner response board</h3><span className="subtle-badge">{Math.floor(simulated / 3600)}h {Math.floor(simulated % 3600 / 60)}m · demo ×2700</span></div>{partners.map(p => { const reply = item.quotes?.partners.find(r => r.id === p.id); return <div className="partner-status-row" key={p.id}><strong>{p.name}</strong><span>{reply ? label(reply.state) : 'Sent · awaiting reply'}</span></div>; })}</section>;
}
