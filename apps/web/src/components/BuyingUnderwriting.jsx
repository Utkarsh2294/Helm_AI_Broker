import React, { useState } from 'react';
import { api } from '../api';
import BuyingMedicalResponse from './BuyingMedicalResponse';

export default function BuyingUnderwriting({ item, document, user, onChanged }) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  if (
    !['moratorium_declaration', 'fmu_questionnaire'].includes(document.doc_type) ||
    item.closed_at ||
    !['authorised_broker', 'lead_broker', 'senior_broker', 'admin'].includes(user.role)
  )
    return null;
  async function act(action) {
    setBusy(true);
    setError('');
    try {
      await api(`/policy-buying/cases/${item.case_id}/declaration/${action}`, {
        method: 'POST',
        body: {
          expected_version: item.version,
          document_id: document.id,
          ...(action === 'complete' ? { confirm_signature: true } : {}),
        },
      });
      await onChanged();
    } catch (cause) {
      setError(cause.message);
      onChanged();
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {document.status === 'sent' && (
        <button className="button small" disabled={busy} onClick={() => act('complete')}>
          {document.doc_type === 'fmu_questionnaire'
            ? 'Simulate: consumer completes and signs questionnaire'
            : 'Simulate: consumer accepts and signs declaration'}
        </button>
      )}
      {document.status === 'returned' && (
        <div className="pb-demo">
          <h4>Consumer completed this version</h4>
          <p>Your final review is required before banking details can be requested.</p>
          {document.doc_type === 'fmu_questionnaire' && (
            <BuyingMedicalResponse caseId={item.case_id} />
          )}
          <button className="button primary" disabled={busy} onClick={() => act('approve')}>
            Approve underwriting declaration
          </button>
        </div>
      )}
    </div>
  );
}
