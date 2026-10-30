import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Download, ArrowUpRight } from 'lucide-react';
import { api, label } from '../api';
import BottomSheet from './BottomSheet';
import Reauthenticate from './Reauthenticate';
import TextArea from './TextArea';

export default function DemoShowcase({ user }) {
  const [data, setData] = useState(null),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [documents, setDocuments] = useState([]),
    [checks, setChecks] = useState([]),
    [note, setNote] = useState(''),
    [verify, setVerify] = useState(false);
  const load = () =>
    api('/demo/showcase')
      .then(setData)
      .catch((cause) => setError(cause.message));
  useEffect(() => {
    load();
  }, []);
  const toggle = (value, values, setter) =>
    setter(values.includes(value) ? values.filter((id) => id !== value) : [...values, value]);
  async function create() {
    setBusy(true);
    setError('');
    try {
      setData(await api('/demo/showcase', { method: 'POST' }));
    } catch (cause) {
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  }
  async function record(proof) {
    setBusy(true);
    setError('');
    try {
      setData(
        await api('/demo/showcase/reviews', {
          method: 'POST',
          headers: { 'X-Step-Up': proof },
          body: {
            review_hash: data.review_hash,
            document_ids: documents,
            acknowledgements: checks,
            note: note.trim(),
          },
        }),
      );
      setVerify(false);
    } catch (cause) {
      setVerify(false);
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  }
  if (!data)
    return (
      <p role={error ? 'alert' : 'status'}>{error || 'Loading the fictional pilot showcase…'}</p>
    );
  const reviewer = ['compliance_officer', 'legal_reviewer'].includes(user.role);
  const alreadyReviewed = data.reviews.some((review) => review.user_id === user.id);
  const complete =
    documents.length === data.documents.length &&
    checks.length === Object.keys(data.checklist).length &&
    note.trim().length >= 20;
  return (
    <>
      <div className="notice warning">
        <div>
          <strong>Fictional demonstration only</strong>
          <p>
            These documents, broker references and review decisions show how the workflow works.
            They grant no legal, FCA, insurer or live-launch approval.
          </p>
        </div>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <section className="surface demo-showcase" aria-labelledby="demo-journey-title">
        <h2 id="demo-journey-title">From documents to an accountable decision</h2>
        <ol className="demo-journey">
          <li>
            <strong>1. Start the fictional case</strong>
            <p>Morgan Demo's renewal, stated needs and budget become a sourced fact-find.</p>
            {!data.case_id && user.role === 'authorised_broker' && (
              <button className="button primary" disabled={busy} onClick={create}>
                Create showcase case
              </button>
            )}
            {!data.case_id && user.role !== 'authorised_broker' && (
              <p>Sign in as a demo adviser to create the showcase.</p>
            )}
            {data.case_id && (
              <Link className="button" to={`/case/${data.case_id}`}>
                Open showcase case <ArrowUpRight size={16} />
              </Link>
            )}
          </li>
          <li>
            <strong>2. Complete the five-agent journey</strong>
            <p>
              Sign G0, release G1, review all five plans, select three, confirm suitability and
              authenticate for G2. Agent 5 only proposes changes.
            </p>
            <span className="subtle-badge">
              {data.workflow_published
                ? 'G2 publication recorded'
                : label(data.case_state || 'Case not started')}
            </span>
          </li>
          <li>
            <strong>3. Review the documents</strong>
            <p>
              Download each sample, inspect the case evidence, and acknowledge the limitations
              below.
            </p>
          </li>
          <li>
            <strong>4. Record two independent demo decisions</strong>
            <p>
              Use compliance@helm.demo and legal@helm.demo as separate personas. Both verify their
              own decision. Actual launch remains blocked.
            </p>
          </li>
        </ol>
        <button className="text-button" disabled={busy} onClick={load}>
          Refresh progress
        </button>
      </section>
      <section className="surface demo-showcase" aria-labelledby="demo-documents-title">
        <h2 id="demo-documents-title">Demonstration document pack</h2>
        <p className="muted">
          Every PDF is labelled fictional. Its SHA-256 is bound to the review manifest.
        </p>
        <ul className="demo-document-list">
          {data.documents.map((document) => (
            <li key={document.id}>
              <div>
                <strong>{document.title}</strong>
                <p className="muted">{document.stage}</p>
                <details>
                  <summary>Document fingerprint</summary>
                  <code className="demo-hash">{document.sha256}</code>
                </details>
              </div>
              <a className="button" href={document.url} download>
                <Download size={16} />
                Download {document.id} PDF
              </a>
            </li>
          ))}
        </ul>
      </section>
      <section className="surface demo-showcase" aria-labelledby="demo-review-title">
        <h2 id="demo-review-title">Pilot review rehearsal</h2>
        <p>
          Current case audit: {data.chain_verified ? 'verified' : 'not yet available'}. Live release
          approval: <strong>not granted</strong>.
        </p>
        {data.reviews.map((review) => (
          <p key={review.user_id}>
            {label(review.role)} · {review.name} · {new Date(review.at).toLocaleString('en-GB')} ·
            fictional scope
          </p>
        ))}
        {data.demo_ready && (
          <div className="notice">
            <strong>Demonstration review complete. This is not a live go-live decision.</strong>
          </div>
        )}
        {reviewer && !alreadyReviewed && (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              setVerify(true);
            }}
          >
            <fieldset disabled={!data.workflow_published || busy}>
              <legend>Confirm your review of this version</legend>
              {data.documents.map((document) => (
                <label className="check-row" key={document.id}>
                  <input
                    type="checkbox"
                    checked={documents.includes(document.id)}
                    onChange={() => toggle(document.id, documents, setDocuments)}
                  />
                  I reviewed: {document.title}
                </label>
              ))}
              {Object.entries(data.checklist).map(([key, text]) => (
                <label className="check-row" key={key}>
                  <input
                    type="checkbox"
                    checked={checks.includes(key)}
                    onChange={() => toggle(key, checks, setChecks)}
                  />
                  {text}
                </label>
              ))}
              <TextArea
                label="Demo reviewer note"
                required
                minLength={20}
                maxLength={2000}
                value={note}
                onChange={(event) => setNote(event.target.value)}
              />
              <button className="button primary" disabled={!complete || busy}>
                Verify and record demo review
              </button>
            </fieldset>
            {!data.workflow_published && (
              <p className="muted">Complete G2 publication before recording a pilot review.</p>
            )}
          </form>
        )}
        {!reviewer && (
          <p className="muted">
            After publication, sign out and use the separate demo compliance and legal personas to
            rehearse review.
          </p>
        )}
      </section>
      <BottomSheet
        open={verify}
        onClose={() => !busy && setVerify(false)}
        title="Confirm fictional pilot review"
        description="This decision is bound to the current documents and broker-approved pack."
      >
        <Reauthenticate
          title="Verify your demo review"
          actionLabel="Record fictional review"
          onVerified={record}
        />
      </BottomSheet>
    </>
  );
}
