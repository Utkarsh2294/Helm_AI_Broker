import React, { useEffect, useRef, useState } from 'react';
import { api, money, label } from '../api';
export default function QuickLook({ item, onClose, onOpen }) {
  const dialog = useRef(null), [detail, setDetail] = useState(null);
  useEffect(() => { dialog.current.showModal(); api(`/cases/${item.id}`).then(setDetail).catch(() => {}); }, [item.id]);
  return <dialog ref={dialog} className="quick-look" onCancel={onClose} aria-label="Quick look"><span className="eyebrow">QUICK LOOK</span><h2>{item.name}</h2><p className="muted">{label(item.cover_type)} · {item.postcode} · {label(item.state)}</p>{detail?.dnr && <p>Annual budget {money(detail.dnr.needs.budget_annual_pence)} · Priorities: {detail.dnr.needs.priorities.map(label).join(', ')}</p>}<div className="button-row"><button className="button primary" onClick={() => onOpen(item.id)}>Open case</button><button className="button" onClick={onClose}>Close</button></div></dialog>;
}
