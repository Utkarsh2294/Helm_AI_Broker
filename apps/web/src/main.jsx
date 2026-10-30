import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useSessionStore } from './session-store';
const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1 } } });
import React, { useEffect, useState, lazy, Suspense } from 'react';
import { createRoot } from 'react-dom/client';
import {
  ArrowRight,
  ShieldCheck,
  LogOut,
  LayoutDashboard,
  Workflow,
  Building2,
  ChartNoAxesCombined,
  History,
  Compass,
  HelpCircle,
  X,
} from 'lucide-react';
import { api, label } from './api';
import './styles.css';
import './design/tokens.css';
import './design/semantic.css';
import './design/light.css';
import ThemeToggle from './design/theme';
const SecuritySettings = lazy(() => import('./security-settings'));
import { Settings } from 'lucide-react';
import { MotionConfig } from 'framer-motion';
import { BrowserRouter, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Login, SignedOut, safeNext } from './auth-pages';
import './design/components.css';

export function Brand({ light = false }) {
  return (
    <div className={`brand ${light ? 'light' : ''}`}>
      <span className="brand-symbol">
        <Compass size={23} strokeWidth={1.5} />
      </span>
      <span>
        helm<span className="brand-dot">.</span>
      </span>
      <small>BROKER</small>
    </div>
  );
}

const navigation = [
  ['workspace', 'Workspace', LayoutDashboard],
  ['agents', 'Agent team', Workflow],
  ['partners', 'Partners', Building2],
  ['learning', 'Learning & insights', ChartNoAxesCombined],
  ['audit', 'Activity & audit', History],
  ['security', 'Security & devices', Settings],
];

function App() {
  const { user, setUser } = useSessionStore();
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate(),
    location = useLocation();
  const routes = {
    workspace: '/queue',
    agents: '/agents',
    partners: '/partners',
    learning: '/learning',
    audit: '/audit',
    security: '/security',
  };
  const page = Object.keys(routes).find((key) => routes[key] === location.pathname) || 'workspace';
  const setPage = (key) => navigate(routes[key] || '/queue');
  const [guide, setGuide] = useState(false);
  const [logoutError, setLogoutError] = useState('');
  useEffect(() => {
    api('/auth/session')
      .then((data) => setUser(data.user))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    const expired = () => {
      queryClient.clear();
      setUser(null);
      navigate('/signed-out/session-expired', { replace: true });
    };
    window.addEventListener('helm:session-expired', expired);
    return () => window.removeEventListener('helm:session-expired', expired);
  }, [navigate, setUser]);
  async function logout() {
    try {
      await api('/auth/logout', { method: 'POST' });
      queryClient.clear();
      window.location.replace('/signed-out/voluntary');
    } catch (e) {
      setLogoutError(e.message);
    }
  }
  if (loading)
    return (
      <main className="loading-screen" aria-live="polite">
        Opening your workspace…
      </main>
    );
  if (location.pathname.startsWith('/signed-out')) return <SignedOut />;
  if (!user && location.pathname !== '/login')
    return (
      <Navigate
        replace
        to={
          '/login' +
          (location.pathname === '/'
            ? ''
            : '?next=' + encodeURIComponent(location.pathname + location.search))
        }
      />
    );
  if (!user) return <Login onLogin={setUser} />;
  if (location.pathname === '/' || location.pathname === '/login')
    return <Navigate replace to={safeNext(new URLSearchParams(location.search).get('next'))} />;
  return (
    <div className="app-layout">
      <a className="skip-link" href="#main">
        Skip to workspace
      </a>
      <aside className="sidebar">
        <Brand light />
        <div className="team-label">
          <span className="team-avatar">H</span>
          <div>
            Helm advisory<small>UK private medical insurance</small>
          </div>
        </div>
        <p className="nav-caption">YOUR WORKSPACE</p>
        <nav aria-label="Main navigation">
          {navigation.map(([key, title, Icon]) => (
            <button
              key={key}
              className={`nav-item ${page === key ? 'active' : ''}`}
              aria-current={page === key ? 'page' : undefined}
              onClick={() => setPage(key)}
            >
              <Icon size={18} />
              {title}
              {key === 'agents' && <span className="nav-count">5</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="human-note">
            <ShieldCheck size={21} />
            <strong>
              Powered by intelligence.
              <br />
              Guided by you.
            </strong>
            <p>Every recommendation ends with a human decision.</p>
          </div>
          <button className="nav-item" onClick={() => setGuide(true)}>
            <HelpCircle size={18} />
            Demo guide
          </button>
          <div className="user-row">
            <span className="user-avatar">
              {user.name
                .split(' ')
                .map((n) => n[0])
                .join('')}
            </span>
            <div>
              {user.name}
              <small>{label(user.role)}</small>
            </div>
            <button className="icon-button" aria-label="Sign out" title="Sign out" onClick={logout}>
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-wrap">
        <header className="topbar">
          <span>
            Helm advisory <span className="divider">/</span>{' '}
            <strong>{navigation.find((n) => n[0] === page)[1]}</strong>
          </span>
          <div className="topbar-actions">
            <ThemeToggle />
            <span className="demo-badge">
              <span className="status-dot" /> Demo environment
            </span>
          </div>
        </header>
        {logoutError && (
          <p role="alert" className="error">
            {logoutError}
          </p>
        )}
        <main id="main" className="main-content">
          <Suspense fallback={<p role="status">Loading workspace…</p>}>
            {page === 'security' ? (
              <SecuritySettings />
            ) : (
              <Workspace page={page} user={user} setPage={setPage} />
            )}
          </Suspense>
        </main>
        <footer className="app-footer">
          <span>
            HELM BROKER <span>·</span> A little more intelligence. A lot more confidence.
          </span>
          <span>Fictional data · Human approval required</span>
        </footer>
      </div>
      {guide && (
        <div className="modal-backdrop" onClick={() => setGuide(false)}>
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label="Demo guide"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="close-button"
              aria-label="Close demo guide"
              onClick={() => setGuide(false)}
            >
              <X />
            </button>
            <span className="eyebrow">A QUICK INTRODUCTION</span>
            <h2>Your five-agent team.</h2>
            <p>
              Open a case, review the fact-find and sign it off. Release a demo RFQ to five
              fictional partners. Quotes arrive in about six seconds with the default demo clock.
            </p>
            <p>
              Compare the top five policies, select three, give feedback, and review the suitability
              statement. Re-enter your password to approve simulated delivery.
            </p>
            <p>
              Learning produces proposals only. No real insurers, emails or medical interpretation
              are used.
            </p>
            <button className="button primary" onClick={() => setGuide(false)}>
              Explore workspace
              <ArrowRight size={16} />
            </button>
          </section>
        </div>
      )}
    </div>
  );
}

// Workspace is kept separate so the authenticated shell remains small.
const Workspace = lazy(() => import('./workspace'));
createRoot(document.getElementById('root')).render(
  <QueryClientProvider client={queryClient}>
    <MotionConfig reducedMotion="user">
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </MotionConfig>
  </QueryClientProvider>,
);
