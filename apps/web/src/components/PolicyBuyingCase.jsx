import React, { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { api, money } from '../api';
import { buyingStages, stageLabels } from './PolicyBuying';

export default function PolicyBuyingCase({ caseId }) {
  const heading = useRef(null);
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
                {document.content.sections?.map((section) => (
                  <div key={section.heading}>
                    <h4>{section.heading}</h4>
                    <p>{section.text}</p>
                  </div>
                ))}
              </article>
            ))
          ) : (
            <p role="status">The demo agent is preparing the document drafts.</p>
          )}
        </section>
      </div>
    </>
  );
}
