import React, { useState } from 'react';
import { api } from '../api';

export default function BuyingSubmission({ item, onChanged }) {
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  if (item.stage !== 'SUBMISSION_PACKAGE_READY') return null;
  const document = item.documents.find((row) => row.doc_type === 'submission_package');
  async function review(send = false) {
    setBusy(true);
    setError('');
    try {
      await api(
        `/policy-buying/cases/${item.case_id}/submission/${send === true ? 'send' : 'review'}`,
        {
          method: 'POST',
          body: {
            expected_version: item.version,
            document_id: document.id,
            ...(send === true ? { package_hash: item.package_hash, confirm_send: true } : {}),
          },
        },
      );
      await onChanged();
    } catch (cause) {
      setError(cause.message);
      onChanged();
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      className="pb-demo"
      id="buying-submission"
      tabIndex={-1}
      aria-label="Final submission review"
    >
      <h3>Ready for your final review</h3>
      <p>The demo agent has prepared everything for {item.plan.insurerId}.</p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <button className="button primary" disabled={busy || !document} onClick={review}>
        Review &amp; Send
      </button>
      {item.submission_reviewed && document && (
        <div>
          <h4>Read-only package preview</h4>
          {document.content.sections.map((section) => (
            <div key={section.heading}>
              <strong>{section.heading}</strong>
              <p>{section.text}</p>
            </div>
          ))}
          <ul>
            {Object.entries(document.content.manifest.documents).map(([kind, version]) => (
              <li key={kind}>
                <a
                  href={`#document-${kind}`}
                  onClick={() =>
                    window.document
                      .getElementById(`document-${kind}`)
                      ?.querySelector('details')
                      ?.setAttribute('open', '')
                  }
                >
                  Review {kind.replaceAll('_', ' ')} · v{version.version}
                </a>
              </li>
            ))}
          </ul>
          <p>Edits reopen the affected confirmations and require a new package review.</p>
          <button className="button primary" disabled={busy} onClick={() => review(true)}>
            Send to mock insurer
          </button>
        </div>
      )}
    </section>
  );
}
