import React, { useEffect, useState } from 'react';
import { api, label } from '../api';

export default function CaseDocuments({ item, revealed, onReveal, editable }) {
  const [documents, setDocuments] = useState([]),
    [file, setFile] = useState(null),
    [category, setCategory] = useState('renewal'),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  async function load() {
    try {
      setDocuments(await api(`/cases/${item.id}/documents`));
    } catch (cause) {
      setError(cause.message);
    }
  }
  useEffect(() => {
    load();
  }, [item.id]);
  async function upload(event) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError('');
    try {
      if (file.size > 1000000) throw new Error('Choose a document up to 1 MB.');
      const mime =
        file.type || (file.name.toLowerCase().endsWith('.pdf') ? 'application/pdf' : 'text/plain');
      if (!['application/pdf', 'text/plain'].includes(mime))
        throw new Error('Choose a PDF or UTF-8 text document.');
      const encoded = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.slice(reader.result.indexOf(',') + 1));
        reader.onerror = () => reject(new Error('The selected file could not be read.'));
        reader.readAsDataURL(file);
      });
      await api(`/cases/${item.id}/documents`, {
        method: 'POST',
        body: { mime, category, content_base64: encoded },
      });
      setFile(null);
      await load();
    } catch (cause) {
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="source-details" aria-labelledby="case-documents-title">
      <h3 id="case-documents-title">Source documents</h3>
      <p className="muted">
        PDF text layers and UTF-8 text are parsed locally. Scans need human transcription. Facts
        require broker verification; uploading never changes the fact-find automatically.
      </p>
      {!revealed && (
        <button className="text-button" onClick={onReveal}>
          Verify access to sensitive documents
        </button>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <ul>
        {documents.map((document) => (
          <li key={document.id}>
            {label(document.category)} · {document.pages} pages · <code>{document.source}</code>
            {revealed && (
              <a
                className="button small"
                href={`/api/v1/cases/${item.id}/documents/${document.id}`}
                download
              >
                Download original document
              </a>
            )}
          </li>
        ))}
      </ul>
      {editable && (
        <form onSubmit={upload}>
          <label>
            Document type
            <select value={category} onChange={(event) => setCategory(event.target.value)}>
              {['renewal', 'policy', 'supporting'].map((value) => (
                <option key={value} value={value}>
                  {label(value)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Source document (PDF or text, up to 1 MB)
            <input
              type="file"
              accept=".pdf,.txt,application/pdf,text/plain"
              disabled={!revealed || busy}
              onChange={(event) => setFile(event.target.files[0] || null)}
            />
          </label>
          <button className="button" disabled={!revealed || busy || !file}>
            {busy ? 'Parsing locally…' : 'Upload for broker review'}
          </button>
        </form>
      )}
    </section>
  );
}
