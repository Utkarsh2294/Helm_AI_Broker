import React, { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useLocation } from 'react-router-dom';
import { api, money } from '../api';
import { buyingStages, stageLabels } from './PolicyBuying';
import BuyingFeed from './BuyingFeed';
import BuyingDocumentActions from './BuyingDocumentActions';
import BuyingConsumerResponse from './BuyingConsumerResponse';
import BuyingUnderwriting from './BuyingUnderwriting';
import BuyingBanking from './BuyingBanking';
import BuyingSubmission from './BuyingSubmission';
import { RichText } from './BuyingRichText';
import { useState } from 'react';

export default function PolicyBuyingCase({ caseId, user }) {
  const location = useLocation();
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
  const requestedStep = new URLSearchParams(location.search).get('step');
  useEffect(() => {
    if (!query.data?.id || !requestedStep) return;
    const targets = {
      ipid: 'document-ipid',
      banking: 'buying-banking',
      submission: 'buying-submission',
    };
    const target =
      requestedStep === 'underwriting'
        ? window.document.querySelector('.pb-document details[open]')?.closest('article')
        : window.document.getElementById(targets[requestedStep]);
    if (!target) return;
    target.querySelector('details')?.setAttribute('open', '');
    target.focus({ preventScroll: true });
    target.scrollIntoView({ block: 'start' });
  }, [query.data?.id, requestedStep]);
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
  const declarationKind =
    item.underwriting_basis === 'fmu' ? 'fmu_questionnaire' : 'moratorium_declaration';
  const activeDocument = ['IPID_DRAFTING', 'AWAITING_IPID_CONFIRMATION'].includes(item.stage)
    ? 'ipid'
    : item.stage === 'UNDERWRITING_IN_PROGRESS'
      ? item.documents.find((row) => row.doc_type === 'toba')?.status === 'confirmed'
        ? declarationKind
        : 'toba'
      : item.stage === 'AWAITING_BANKING_DETAILS'
        ? item.banking_received
          ? 'banking_summary'
          : 'banking_request'
        : 'submission_package';
  return (
    <>
      <Link className="button small" to={item.closed_at ? '/closed-cases' : '/policy-buying'}>
        {item.closed_at ? 'Back to Closed Cases' : 'Back to Policy Buying'}
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
      {item.closed_at && (
        <section className="pb-success" aria-label="Demo policy issued">
          <h2>Demo policy issued</h2>
          <p>
            <strong>{item.policy_number}</strong>
          </p>
          <p>The workflow is complete. No real policy was purchased.</p>
          {item.confirmation_message && (
            <details>
              <summary>View local confirmation email</summary>
              <p>Stored in the demo outbox only; no email was sent.</p>
              <p>To: {item.confirmation_message.to}</p>
              <h3>{item.confirmation_message.subject}</h3>
              <p>{item.confirmation_message.message}</p>
              <a
                className="button small"
                href={`/api/v1/policy-buying/cases/${caseId}/documents/${item.confirmation_message.ipid_document_id}.pdf`}
                download
              >
                Download final accepted IPID
              </a>
            </details>
          )}
        </section>
      )}
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
          <Link
            className="button small"
            to={`/case/${caseId}?view=audit`}
            state={{ returnQueuePath: `/policy-buying/cases/${caseId}` }}
          >
            Case audit trail
          </Link>
        </aside>
        <section className="pb-working" aria-label="Buying steps">
          {!item.baseline_acknowledged && (
            <div className="pb-demo">
              <h3>Review the underwriting baseline</h3>
              <p>
                {item.underwriting_basis === 'moratorium'
                  ? 'This consumer chose Moratorium underwriting. In this fictional demonstration, conditions present, symptomatic or treated in the previous five years are excluded until two continuous years without related treatment, medication or advice. Actual insurer terms must be checked.'
                  : 'This consumer chose Full Medical Underwriting. They must provide fresh answers to a medical questionnaire. The insurer determines any personal exclusions before cover is issued; the demo agent does not interpret medical answers.'}
              </p>
              <button
                className="button primary"
                onClick={async () => {
                  try {
                    await api(`/policy-buying/cases/${caseId}/baseline`, {
                      method: 'POST',
                      body: { expected_version: item.version },
                    });
                    setActionError('');
                    query.refetch();
                  } catch (cause) {
                    setActionError(cause.message);
                    query.refetch();
                  }
                }}
              >
                I acknowledge this underwriting basis
              </button>
            </div>
          )}
          {actionError && (
            <p role="alert" className="error">
              {actionError}
            </p>
          )}
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
          <BuyingBanking item={item} onChanged={() => query.refetch()} />
          <BuyingSubmission item={item} onChanged={() => query.refetch()} />
          {item.documents.length ? (
            item.documents.map((document) => (
              <article
                className="pb-document"
                key={document.id}
                id={`document-${document.doc_type}`}
                tabIndex={-1}
              >
                <details open={document.doc_type === activeDocument}>
                  <summary>
                    <h3>{document.content.title || document.doc_type.replaceAll('_', ' ')}</h3>
                    <span>
                      Version {document.version} · {document.status}
                    </span>
                  </summary>
                  <p>
                    Version {document.version} · {document.status}
                  </p>
                  <a
                    className="button small"
                    href={`/api/v1/policy-buying/cases/${caseId}/documents/${document.id}.pdf`}
                    download
                  >
                    Download demo PDF
                  </a>
                  {document.content.sections?.map((section) => (
                    <div key={section.heading}>
                      <h4>{section.heading}</h4>
                      <RichText value={section.text} />
                    </div>
                  ))}
                  <BuyingDocumentActions
                    item={item}
                    document={document}
                    user={user}
                    onChanged={() => query.refetch()}
                  />
                  <BuyingConsumerResponse
                    item={item}
                    document={document}
                    onChanged={() => query.refetch()}
                  />
                  <BuyingUnderwriting
                    item={item}
                    document={document}
                    user={user}
                    onChanged={() => query.refetch()}
                  />
                </details>
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
