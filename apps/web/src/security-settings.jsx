import React, { useEffect, useState } from 'react';
import { Fingerprint, ShieldCheck, Monitor, KeyRound } from 'lucide-react';
import { startRegistration } from '@simplewebauthn/browser';
import { api } from './api';

export default function SecuritySettings() {
  const [devices, setDevices] = useState([]), [error, setError] = useState(''), [message, setMessage] = useState('');
  const [setup, setSetup] = useState(null), [code, setCode] = useState(''), [codes, setCodes] = useState([]), [busy, setBusy] = useState(false);
  const refresh = () => api('/auth/devices').then(setDevices).catch(e => setError(e.message));
  useEffect(() => { refresh(); }, []);
  async function run(task) { setBusy(true); setError(''); try { await task(); } catch (e) { setError(e.name === 'NotAllowedError' ? 'Passkey ceremony was cancelled.' : e.message); } finally { setBusy(false); } }
  return <><div className="page-heading"><div><span className="eyebrow">YOUR ACCOUNT, PROTECTED</span><h1>Security & devices.</h1><p className="muted">Manage your passkeys, authenticator and active sessions.</p></div></div>
    {error && <p className="error" role="alert">{error}</p>}{message && <p className="notice" role="status">{message}</p>}
    <section className="surface security-section"><Fingerprint/><h2>Sign in with a passkey.</h2><p className="muted">Use Windows Hello, a security key or your device's biometric verification.</p><button className="button primary" disabled={busy} onClick={() => run(async () => { const options = await api('/auth/passkeys/register/options', { method: 'POST' }); const credential = await startRegistration({ optionsJSON: options.options }); await api('/auth/passkeys/register', { method: 'POST', body: { challenge_id: options.challenge_id, credential } }); setMessage('Passkey registered. You can use it on your next sign-in.'); })}>Register a passkey<Fingerprint size={16}/></button></section>
    <section className="surface security-section"><ShieldCheck/><h2>Add an authenticator.</h2><p className="muted">After enrollment, password sign-in and approval re-authentication require an authenticator code.</p>{!setup && !codes.length && <button className="button" disabled={busy} onClick={() => run(async () => setSetup(await api('/auth/totp/setup', { method: 'POST' })))}>Set up authenticator<KeyRound size={16}/></button>}
      {setup && <form onSubmit={e => { e.preventDefault(); run(async () => { const response = await api('/auth/totp/enable', { method: 'POST', body: { code } }); setCodes(response.recovery_codes); setSetup(null); setMessage('Authenticator enabled. Store your recovery codes securely.'); }); }}><p>Enter this key in your authenticator app:</p><code className="secret-key">{setup.secret}</code><p><a href={setup.uri}>Open authenticator app</a></p><label>Authenticator code<input aria-label="Enrollment code" value={code} onChange={e => setCode(e.target.value)} inputMode="numeric" autoComplete="one-time-code" required pattern="[0-9]{6}"/></label><button className="button primary" disabled={busy}>Verify and enable</button></form>}
      {codes.length > 0 && <div><p>Recovery codes · each can be used once. They will not be shown again.</p><pre>{codes.join('\n')}</pre><button className="button" onClick={() => setCodes([])}>I saved these codes</button></div>}
    </section><section className="surface security-section"><Monitor/><h2>Your active devices.</h2>{devices.map(d => <div className="device-row" key={d.id}><div><strong>{d.current ? 'This device' : 'Another device'}</strong><p className="muted">{d.ip} · {d.user_agent}</p></div>{!d.current && <button className="button small danger" onClick={() => run(async () => { await api(`/auth/devices/${d.id}`, { method: 'DELETE' }); await refresh(); })}>Revoke</button>}</div>)}</section></>;
}
