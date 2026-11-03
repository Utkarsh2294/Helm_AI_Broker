import React, { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { api, money } from '../api';
import { buyingStages, stageLabels } from './PolicyBuying';
import BuyingFeed from './BuyingFeed';
import BuyingDocumentActions from './BuyingDocumentActions';
import BuyingConsumerResponse from './BuyingConsumerResponse';
import BuyingUnderwriting from './BuyingUnderwriting';
import { useState } from 'react';

export default function PolicyBuyingCase({ caseId, user }) {
  const heading = useRef(null);
  const [actionError, setActionError] = useState('');
  const query = useQuery({
    queryKey: ['buying-case', caseId],
    queryFn: () => api(`/policy-buying/cases/${caseId}`),
    refetchInterval: 3000,
  });
  useEffect(() => {
    heading.current?.focus();
  }, [query.data?.id]);
  const item = query.data;
  if (query.error)
    return (
      <p role="alert" className="error">
        {query.error.message}
        <button className="button small" onClick={() => query.refetch()}>
          Retry
        </button>
      </p>
    );
  if (!item) return <p role="status">Opening buying case…</p>;
  return (
    <>
      <Link className="button small" to="/policy-buying">
        Back to Policy Buying
      </Link>
      <div className="page-heading">
        <div>
          <span className="eyebrow">POLICY BUYING · FICTIONAL DATA</span>
          <h1 tabIndex={-1} ref={heading}>
            {item.client}
          </h1>
          <p>{stageLabels[buyingStages.indexOf(item.stage)]}</p>
        </div>
      </div>
      <p className="pb-demo">
        <strong>Demo only.</strong> Simulated responses, fictional documents and a mock insurer. No
        live policy or payment.
      </p>
      <div className="pb-workspace">
        <aside className="pb-file" aria-label="Digital client file">
          <h2>Digital client file</h2>
          <dl>
            {Object.entries(item.client_file).map(([key, value]) => (
              <React.Fragment key={key}>
                <dt>{key.replaceAll('_', ' ')}</dt>
                <dd>{value || 'Not supplied'}</dd>
              </React.Fragment>
            ))}
          </dl>
          <h3>Selected plan</h3>
          <p>{item.plan.name}</p>
          <p>{item.plan.insurerId}</p>
          <p>{money(item.plan.annualPremiumPence)} / year</p>
          <h3>Original underwriting preference</h3>
          <p>
            {item.underwriting_basis === 'fmu' ? 'Full Medical Underwriting (FMU)' : 'Moratorium'}
          </p>
          <Link className="button small" to={`/case/${caseId}?view=audit`}>
            Case audit trail
          </Link>
        </aside>
        <section className="pb-working" aria-label="Buying steps">
        {!item.baseline_acknowledged && <div className="pb-demo"><h3>Review the underwriting baseline</h3><p>{item.underwriting_basis === 'moratorium' ? 'This consumer chose Moratorium underwriting. In this fictional demonstration, conditions present, symptomatic or treated in the previous five years are excluded until two continuous years without related treatment, medication or advice. Actual insurer terms must be checked.' : 'This consumer chose Full Medical Underwriting. They must provide fresh answers to a medical questionnaire. The insurer determines any personal exclusions before cover is issued; the demo agent does not interpret medical answers.'}</p><button className="button primary" onClick={async () => { try { await api(`/policy-buying/cases/${caseId}/baseline`, { method: 'POST', body: { expected_version: item.version } }); setActionError(''); query.refetch(); } catch (cause) { setActionError(cause.message); query.refetch(); } }}>I acknowledge this underwriting basis</button></div>}
        {actionError && <p role="alert" className="error">{actionError}</p>}
          <h2>Buying steps</h2>
          <ol className="pb-stepper">
            {stageLabels.map((label, index) => (
              <li
                key={label}
                aria-current={buyingStages[index] === item.stage ? 'step' : undefined}
                className={buyingStages.indexOf(item.stage) >= index ? 'reached' : ''}
              >
                <span>{index + 1}</span>
                {label}
              </li>
            ))}
          </ol>
          {item.documents.length ? (
            item.documents.map((document) => (
              <article
                className="pb-document"
                key={document.id}
                id={`document-${document.doc_type}`}
              >
                <h3>{document.content.title || document.doc_type.replaceAll('_', ' ')}</h3>
                <p>
                  Version {document.version} · {document.status}
                </p>
                  <a className="button small" href={`/api/v1/policy-buying/cases/${caseId}/documents/${document.id}.pdf`} download>Download demo PDF</a>
                {document.content.sections?.map((section) => (
                  <div key={section.heading}>
                    <h4>{section.heading}</h4>
                    <p>{section.text}</p>
                  </div>
                ))}
                  <BuyingDocumentActions item={item} document={document} user={user} onChanged={() => query.refetch()} />
                  <BuyingConsumerResponse item={item} document={document} onChanged={() => query.refetch()} />
                  <BuyingUnderwriting item={item} document={document} user={user} onChanged={() => query.refetch()} />
              </article>
            ))
          ) : (
            <p role="status">The demo agent is preparing the document drafts.</p>
          )}
        </section>
        <BuyingFeed item={item} onRead={() => query.refetch()} />
      </div>
    </>
  );
}
