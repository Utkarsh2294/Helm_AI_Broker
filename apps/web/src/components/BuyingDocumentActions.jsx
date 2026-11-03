import React, { useState } from 'react';
import { api } from '../api';

export default function BuyingDocumentActions({ item, document, onChanged, user }) {
  const [editing, setEditing] = useState(false), [querying, setQuerying] = useState(false), [sections, setSections] = useState(document.content.sections), [instruction, setInstruction] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState('');
  if (item.closed_at || !['authorised_broker','senior_broker','lead_broker','admin'].includes(user.role) || !['ipid','toba','moratorium_declaration','fmu_questionnaire'].includes(document.doc_type)) return null;
  async function act(action, extra = {}) {
    setBusy(true); setError('');
    try { await api(`/policy-buying/cases/${item.case_id}/documents/${document.doc_type}/${action}`, { method: 'POST', body: { expected_version: item.version, document_id: document.id, ...extra } }); setEditing(false); setQuerying(false); await onChanged(); }
    catch (cause) { setError(cause.message); onChanged(); } finally { setBusy(false); }
  }
  const ready = item.baseline_acknowledged && (document.doc_type === 'ipid' ? item.stage === 'IPID_DRAFTING' : item.stage === 'UNDERWRITING_IN_PROGRESS' && (document.doc_type === 'toba' || item.documents.find((row) => row.doc_type === 'toba')?.status === 'confirmed'));
  return <div className="pb-doc-actions">{error && <p className="error" role="alert">{error}</p>}
    {!editing && !querying && <div className="assistant-toolbar"><button className="button primary" disabled={busy || document.status !== 'draft' || !ready} onClick={() => act('send')}>Approve &amp; Send</button><button className="button small" disabled={busy} onClick={() => setQuerying(true)}>Request AI changes</button><button className="button small" disabled={busy} onClick={() => setEditing(true)}>Edit manually</button></div>}
    {editing && <form onSubmit={(event) => { event.preventDefault(); act('edit', { sections }); }}><p>Each saved edit creates a new version and reopens affected confirmations.</p>{sections.map((section, index) => <label className="pb-edit-block" key={section.heading}>{section.heading}<textarea maxLength={2000} required value={section.text} onChange={(event) => setSections((previous) => previous.map((row, position) => position === index ? { ...row, text: event.target.value } : row))}/></label>)}<button className="button primary" disabled={busy}>Save new version</button><button className="button small" type="button" onClick={() => setEditing(false)}>Cancel edit</button></form>}
    {querying && <form onSubmit={(event) => { event.preventDefault(); act('edit', { instruction }); }}><label>Requested changes<textarea maxLength={2200} required value={instruction} onChange={(event) => setInstruction(event.target.value)}/></label><p className="muted">Local demo: use “Section &lt;exact heading&gt;: &lt;replacement wording&gt;”. An external AI provider is not connected.</p><button className="button primary" disabled={busy}>Prepare revised draft</button><button className="button small" type="button" onClick={() => setQuerying(false)}>Cancel request</button></form>}
  </div>;
}
