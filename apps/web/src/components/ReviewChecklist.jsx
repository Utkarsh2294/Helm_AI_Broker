import React, { useState } from 'react';
import { api, label } from '../api';
const sections = ['priorities', 'coverage', 'budget', 'household', 'medical_flag'];
export default function ReviewChecklist({ item, onSaved, onError }) {
  const [checked, setChecked] = useState(item.pack.dnr_sections_confirmed || []);
  const [unmet, setUnmet] = useState(item.pack.unmet_needs_addressed || []);
  const [saving, setSaving] = useState(false);
  const toggle = (values, value) => values.includes(value) ? values.filter(v => v !== value) : [...values, value];
  async function save() { setSaving(true); try { onSaved(await api(`/cases/${item.id}/suitability`, { method: 'PUT', body: { text: item.pack.suitability_final, dnr_sections_confirmed: checked, unmet_needs_addressed: unmet } })); } catch (e) { onError(e.message); } finally { setSaving(false); } }
  return <div className="review-checklist"><h3>Record your review</h3><p className="muted">Confirm each section against the fact-find, then save this review before signing.</p>{sections.map(section => <label className="checkbox-label" key={section}><input type="checkbox" checked={checked.includes(section)} onChange={() => setChecked(toggle(checked, section))}/>{label(section)} reviewed</label>)}{item.pack.unmet_needs.map(n => { const key = `${n.plan_id}:${n.need}`; return <label className="checkbox-label" key={key}><input type="checkbox" checked={unmet.includes(key)} onChange={() => setUnmet(toggle(unmet, key))}/>Addressed {label(n.need)} for {n.plan_id}</label>; })}<button className="button" disabled={saving || checked.length !== 5 || unmet.length !== item.pack.unmet_needs.length} onClick={save}>Save review confirmations</button>{item.pack.suitability_diff?.length > 0 && <details><summary>Changes from the agent draft</summary><pre>{item.pack.suitability_diff.join('\n')}</pre></details>}<p className="muted">Cancellation: {item.pack.manifest?.cancellation?.text || item.pack.manifest?.cancellation}</p></div>;
}
