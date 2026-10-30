import React, { useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  startAuthentication,
  browserSupportsWebAuthnAutofill,
  WebAuthnAbortService,
} from '@simplewebauthn/browser';
import { z } from 'zod';
import { Compass, Fingerprint, ShieldCheck, ArrowRight } from 'lucide-react';
import { api } from './api';
import Input from './components/Input';
import Button from './components/Button';
import BottomSheet from './components/BottomSheet';
import MfaCodeInput from './components/MfaCodeInput';
import PasskeyOrigin, { passkeysAvailable } from './components/PasskeyOrigin';

export function safeNext(value) {
  return typeof value === 'string' &&
    /^\/(queue|partners|learning|security|case\/[^/?#]+)(\?[^#]*)?$/.test(value) &&
    !value.includes('\\')
    ? value
    : '/queue';
}

export function SignedOut() {
  const location = useLocation();
  const reason = location.pathname.split('/').at(-1);
  const [headline, message] = {
    voluntary: [
      "You've been signed out.",
      'Your work has been saved. Sign in when you are ready to continue.',
    ],
    'session-expired': [
      'Your session timed out for security.',
      'Sign in again to return to your workspace.',
    ],
    'step-up-failed': [
      'Step-up verification failed.',
      'Any pending approval was cancelled. Your recommendation remains unpublished.',
    ],
  }[reason] || ['You are signed out.', 'Sign in to return to your workspace.'];
  return (
    <main className="signed-out">
      <Compass size={40} />
      <span className="eyebrow">HELM BROKER</span>
      <h1>{headline}</h1>
      <p>{message}</p>
      <Link className="button primary" to="/login">
        Sign back in <ArrowRight size={18} />
      </Link>
    </main>
  );
}

export function Login({ onLogin }) {
  const [email, setEmail] = useState('broker@helm.demo'),
    [password, setPassword] = useState('');
  const [challenge, setChallenge] = useState(''),
    [recovery, setRecovery] = useState(false),
    [code, setCode] = useState('');
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const active = useRef(true),
    working = useRef(false);
  const navigate = useNavigate(),
    location = useLocation();
  const next = safeNext(new URLSearchParams(location.search).get('next'));
  function complete(user) {
    flushSync(() => {
      onLogin(user);
      navigate(next, { replace: true });
    });
  }
  async function passkey(conditional = false) {
    if (!conditional) {
      setBusy(true);
      setError('');
    }
    try {
      const options = await api('/auth/passkey/options', { method: 'POST', body: {} });
      if (!active.current) return;
      const credential = await startAuthentication({
        optionsJSON: options.options,
        useBrowserAutofill: conditional,
      });
      const result = await api('/auth/passkey/verify', {
        method: 'POST',
        body: { challenge_id: options.challenge_id, credential },
      });
      if (active.current) complete(result.user);
    } catch (cause) {
      if (!conditional && active.current)
        setError(
          cause.name === 'NotAllowedError' ? 'Passkey sign-in was cancelled.' : cause.message,
        );
    } finally {
      if (!conditional && active.current) setBusy(false);
    }
  }
  useEffect(() => {
    active.current = true;
    if (passkeysAvailable())
      browserSupportsWebAuthnAutofill()
        .then((supported) => {
          if (supported && active.current) passkey(true);
        })
        .catch(() => {});
    return () => {
      active.current = false;
      WebAuthnAbortService.cancelCeremony();
    };
  }, []);
  async function submit(event, completedCode) {
    event?.preventDefault();
    if (working.current) return;
    const parsed = z
      .object({ email: z.email(), password: z.string().min(1) })
      .safeParse({ email, password });
    if (!challenge && !parsed.success) {
      setError('Enter a valid work email and password.');
      return;
    }
    working.current = true;
    setBusy(true);
    setError('');
    WebAuthnAbortService.cancelCeremony();
    try {
      const result = await api(
        challenge ? (recovery ? '/auth/recovery' : '/auth/totp/verify') : '/auth/password',
        {
          method: 'POST',
          body: challenge
            ? { challenge_id: challenge, code: completedCode || code }
            : { email, password },
        },
      );
      if (result.requires_totp) {
        setChallenge(result.challenge_id);
        setCode('');
      } else complete(result.user);
    } catch (cause) {
      setError(cause.message);
    } finally {
      setBusy(false);
      working.current = false;
    }
  }
  return (
    <main className="login-layout">
      <section className="login-story">
        <div className="brand light">
          <Compass />
          <strong>helm.</strong>
          <small>BROKER</small>
        </div>
        <div className="story-content">
          <span className="eyebrow">EXPERT JUDGEMENT. EXTRAORDINARY SUPPORT.</span>
          <h1>
            More clarity.
            <br />
            More confidence.
            <br />
            <em>More human.</em>
          </h1>
          <p>
            Five specialist agents do the groundwork.
            <br />
            You make the decisions that matter.
          </p>
        </div>
        <footer>
          <ShieldCheck size={18} /> A dedicated workspace for trusted advice.
        </footer>
      </section>
      <section className="login-form-wrap">
        <div className="login-form">
          <span className="pill">BROKER WORKSPACE</span>
          <h2>Welcome back.</h2>
          <p className="muted">Your next great recommendation starts here.</p>
          <Button fullWidth disabled={busy || !passkeysAvailable()} onClick={() => passkey()}>
            <Fingerprint size={18} />
            Continue with passkey
          </Button>
          <PasskeyOrigin />
          <form onSubmit={submit}>
            <Input
              label="Email address"
              type="email"
              autoComplete="username webauthn"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
            <Input
              label="Password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
            {error && !challenge && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <Button type="submit" variant="primary" fullWidth loading={busy}>
              Sign in to your workspace
              <ArrowRight size={18} />
            </Button>
          </form>
          <div className="demo-credentials">
            <strong>Explore the demo</strong>
            <p>Fictional cases. All five agents. You stay in control.</p>
            <Button
              variant="ghost"
              onClick={() => {
                setEmail('broker@helm.demo');
                setPassword('HelmDemo!2026');
              }}
            >
              Fill demo credentials <ArrowRight size={14} />
            </Button>
          </div>
          <small className="login-footnote">
            Demo environment · No real policy advice or delivery
          </small>
        </div>
      </section>
      <BottomSheet
        open={Boolean(challenge)}
        onClose={() => {
          setChallenge('');
          setCode('');
          setError('');
        }}
        title="Verify your identity"
        description="Enter the code from your authenticator app."
        detent="auto"
      >
        <form onSubmit={submit}>
          {recovery ? (
            <Input
              label="Recovery code"
              autoComplete="one-time-code"
              value={code}
              onChange={(event) => setCode(event.target.value.toUpperCase())}
              required
            />
          ) : (
            <MfaCodeInput
              value={code}
              onChange={setCode}
              onComplete={(value) => submit(null, value)}
              disabled={busy}
            />
          )}
          <div className="code-validity" aria-hidden="true" />
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <Button
            type="submit"
            variant="primary"
            loading={busy}
            disabled={recovery ? code.length < 8 : !/^\d{6}$/.test(code)}
          >
            Verify code
          </Button>
          <Button
            variant="ghost"
            onClick={() => {
              setRecovery(!recovery);
              setCode('');
            }}
          >
            {recovery ? 'Use authenticator' : 'Use a recovery code'}
          </Button>
        </form>
      </BottomSheet>
    </main>
  );
}
