import React, { useState } from 'react';
import { startAuthentication } from '@simplewebauthn/browser';
import { api } from '../api';
import Button from './Button';
import Input from './Input';
import PasskeyOrigin, { passkeysAvailable } from './PasskeyOrigin';

export default function Reauthenticate({ onVerified }) {
  const [password, setPassword] = useState(''),
    [code, setCode] = useState(''),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  async function verify(passkey = false) {
    setBusy(true);
    setError('');
    try {
      let proof;
      if (passkey) {
        const options = await api('/auth/passkey/options', {
          method: 'POST',
          body: { step_up: true },
        });
        const credential = await startAuthentication({ optionsJSON: options.options });
        proof = await api('/auth/passkey/verify', {
          method: 'POST',
          body: { challenge_id: options.challenge_id, credential },
        });
      } else proof = await api('/auth/step-up', { method: 'POST', body: { password, code } });
      setPassword('');
      setCode('');
      onVerified(proof.step_up_token);
    } catch (cause) {
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="surface security-section">
      <h2>Verify before changing security.</h2>
      <p className="muted">This verification lasts five minutes and is bound to this session.</p>
      <Button disabled={busy || !passkeysAvailable()} onClick={() => verify(true)}>
        Verify with passkey
      </Button>
      <PasskeyOrigin />
      <form
        onSubmit={(event) => {
          event.preventDefault();
          verify();
        }}
      >
        <Input
          type="password"
          label="Security verification password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        <Input
          label="Security verification authenticator code"
          autoComplete="one-time-code"
          inputMode="numeric"
          value={code}
          onChange={(event) => setCode(event.target.value)}
          hint="Use your authenticator code if you enrolled one."
        />
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <Button type="submit" variant="primary" loading={busy}>
          Verify security changes
        </Button>
      </form>
    </section>
  );
}
