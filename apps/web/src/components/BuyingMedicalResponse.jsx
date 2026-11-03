import React, { useEffect, useState } from 'react';
import { api } from '../api';
import Reauthenticate from './Reauthenticate';

export default function BuyingMedicalResponse({ caseId }) {
  const [prompt, setPrompt] = useState(false),
    [response, setResponse] = useState(null);
  useEffect(() => {
    if (!response) return;
    const timeout = setTimeout(
      () => setResponse(null),
      Math.max(0, new Date(response.expires_at) - Date.now()),
    );
    return () => clearTimeout(timeout);
  }, [response]);
  return (
    <div>
      <button
        className="button small"
        onClick={() => {
          setResponse(null);
          setPrompt(true);
        }}
      >
        Verify to view completed FMU answers
      </button>
      {prompt && (
        <Reauthenticate
          title="Verify medical access"
          actionLabel="Reveal fictional FMU answers"
          onVerified={async (proof) => {
            await api(`/cases/${caseId}/medical-access`, {
              method: 'POST',
              headers: { 'X-Step-Up': proof },
            });
            setResponse(await api(`/policy-buying/cases/${caseId}/medical-response`));
            setPrompt(false);
          }}
        />
      )}
      {response && (
        <>
          <p>Untouched seeded demo answers. The agent has not interpreted them.</p>
          <dl>
            {Object.entries(response.answers).map(([key, value]) => (
              <React.Fragment key={key}>
                <dt>{key}</dt>
                <dd>{value}</dd>
              </React.Fragment>
            ))}
          </dl>
          <button className="button small" onClick={() => setResponse(null)}>
            Hide medical answers
          </button>
        </>
      )}
    </div>
  );
}
