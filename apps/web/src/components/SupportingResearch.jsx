import React, { useState } from 'react';
import { Download } from 'lucide-react';
import { api } from '../api';
import AssistantCitations from './AssistantCitations';

export default function SupportingResearch({ pack, caseId }) {
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const rows = pack?.supporting_research || [];
  async function download() {
    setBusy(true);
    setError('');
    try {
      const blob = await api(`/assistant/suitability/${encodeURIComponent(caseId)}.pdf`, {
          responseType: 'blob',
        }),
        url = URL.createObjectURL(blob),
        link = document.createElement('a');
      link.href = url;
      link.download = `helm-suitability-${caseId}.pdf`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (cause) {
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      className="supporting-research"
      aria-label="Supporting research in this recommendation"
    >
      <h3>Supporting research</h3>
      <p className="muted">
        {rows.length
          ? 'These saved answers and their sources are included in this recommendation version. Review them alongside the policy documents.'
          : 'No assistant research was added to this recommendation version.'}
      </p>
      {rows.map((row) => (
        <details key={row.evidence_id}>
          <summary>
            {row.protected && row.question === '[REDACTED]'
              ? 'Protected research — verified access required'
              : row.question}
          </summary>
          <AssistantCitations text={row.answer} sources={row.sources} caseId={caseId} />
          <small>
            {row.timestamp} · {row.model_version} · {row.confidence}
          </small>
        </details>
      ))}
      <button className="button small" disabled={busy} onClick={download}>
        <Download size={15} />
        {busy ? 'Preparing PDF…' : 'Download recommendation PDF'}
      </button>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
