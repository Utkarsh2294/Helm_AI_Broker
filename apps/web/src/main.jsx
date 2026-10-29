import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ArrowRight, ShieldCheck, LockKeyhole, LogOut, LayoutDashboard, Workflow, Building2, ChartNoAxesCombined, History, Compass, HelpCircle, X } from 'lucide-react';
import { api } from './api';
import './styles.css';

export function Brand({ light = false }) {
  return <div className={`brand ${light ? 'light' : ''}`}><span className="brand-symbol"><Compass size={23} strokeWidth={1.5}/></span><span>helm<span className="brand-dot">.</span></span><small>BROKER</small></div>;
}

function Login({ onLogin }) {
  const [email, setEmail] = useState('broker@helm.demo');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError('');
    try { onLogin((await api('/auth/password', { method: 'POST', body: { email, password } })).user); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <main className="login-layout"><section className="login-story"><Brand light/>
    <div className="story-content"><span className="eyebrow">EXPERT JUDGEMENT. EXTRAORDINARY SUPPORT.</span>
      <h1>More clarity.<br/>More confidence.<br/><em>More human.</em></h1>
      <p>Five specialist agents do the groundwork.<br/>You make the decisions that matter.</p>
      <div className="orbit"><Compass size={160} strokeWidth={0.5}/><span>INTELLIGENCE, WITH DIRECTION</span></div>
    </div><footer><ShieldCheck size={16}/> A dedicated workspace for trusted advice.</footer>
  </section><section className="login-form-wrap"><div className="login-form"><span className="pill"><span className="status-dot"/> BROKER WORKSPACE</span>
    <h2>Welcome back.</h2><p className="muted">Your next great recommendation starts here.</p>
    <form onSubmit={submit}><label>Email address<input type="email" autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} required/></label>
      <label>Password<input type="password" autoComplete="current-password" placeholder="Enter your password" value={password} onChange={e => setPassword(e.target.value)} required/></label>
      {error && <p role="alert" className="error">{error}</p>}
      <button className="button primary full" disabled={busy}>{busy ? 'Signing in…' : 'Sign in to your workspace'}<ArrowRight size={17}/></button>
    </form><div className="demo-credentials"><strong>Explore the demo</strong><p>Fictional cases. All five agents. You stay in control.</p>
      <button className="text-button" onClick={() => { setEmail('broker@helm.demo'); setPassword('HelmDemo!2026'); }}>Fill demo credentials <ArrowRight size={14}/></button>
    </div><p className="login-security"><LockKeyhole size={14}/> Encrypted records · Human-approved recommendations</p>
  </div><small className="login-footnote">Demo environment · No real policy advice or delivery</small></section></main>;
}

const navigation = [
  ['workspace', 'Workspace', LayoutDashboard], ['agents', 'Agent team', Workflow], ['partners', 'Partners', Building2],
  ['learning', 'Learning & insights', ChartNoAxesCombined], ['audit', 'Activity & audit', History],
];

function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState('workspace');
  const [guide, setGuide] = useState(false);
  const [logoutError, setLogoutError] = useState('');
  useEffect(() => { api('/auth/session').then(data => setUser(data.user)).catch(() => {}).finally(() => setLoading(false)); }, []);
  async function logout() {
    try { await api('/auth/logout', { method: 'POST' }); setUser(null); }
    catch (e) { setLogoutError(e.message); }
  }
  if (loading) return <main className="loading-screen" aria-live="polite">Opening your workspace…</main>;
  if (!user) return <Login onLogin={setUser}/>;
  return <div className="app-layout"><a className="skip-link" href="#main">Skip to workspace</a>
    <aside className="sidebar"><Brand light/><div className="team-label"><span className="team-avatar">H</span><div>Helm advisory<small>UK private medical insurance</small></div></div>
      <p className="nav-caption">YOUR WORKSPACE</p><nav aria-label="Main navigation">{navigation.map(([key, title, Icon]) => <button key={key} className={`nav-item ${page === key ? 'active' : ''}`} aria-current={page === key ? 'page' : undefined} onClick={() => setPage(key)}><Icon size={18}/>{title}{key === 'agents' && <span className="nav-count">5</span>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="human-note"><ShieldCheck size={21}/><strong>Powered by intelligence.<br/>Guided by you.</strong><p>Every recommendation ends with a human decision.</p></div>
        <button className="nav-item" onClick={() => setGuide(true)}><HelpCircle size={18}/>Demo guide</button>
        <div className="user-row"><span className="user-avatar">{user.name.split(' ').map(n => n[0]).join('')}</span><div>{user.name}<small>Authorised broker</small></div><button className="icon-button" aria-label="Sign out" title="Sign out" onClick={logout}><LogOut size={17}/></button></div>
      </div>
    </aside><div className="main-wrap"><header className="topbar"><span>Helm advisory <span className="divider">/</span> <strong>{navigation.find(n => n[0] === page)[1]}</strong></span><span className="demo-badge"><span className="status-dot"/> Demo environment</span></header>
      {logoutError && <p role="alert" className="error">{logoutError}</p>}
      <main id="main" className="main-content"><Workspace page={page} user={user} setPage={setPage}/></main>
      <footer className="app-footer"><span>HELM BROKER <span>·</span> A little more intelligence. A lot more confidence.</span><span>Fictional data · Human approval required</span></footer>
    </div>{guide && <div className="modal-backdrop" onClick={() => setGuide(false)}><section className="modal" role="dialog" aria-modal="true" aria-label="Demo guide" onClick={e => e.stopPropagation()}><button className="close-button" aria-label="Close demo guide" onClick={() => setGuide(false)}><X/></button><span className="eyebrow">A QUICK INTRODUCTION</span><h2>Your five-agent team.</h2><p>Open a case, review the fact-find and sign it off. Release a demo RFQ to five fictional partners. Quotes arrive in about eight seconds.</p><p>Compare the top five policies, select three, give feedback, and review the suitability statement. Re-enter your password to approve simulated delivery.</p><p>Learning produces proposals only. No real insurers, emails or medical interpretation are used.</p><button className="button primary" onClick={() => setGuide(false)}>Explore workspace<ArrowRight size={16}/></button></section></div>}</div>;
}

// Workspace is kept separate so the authenticated shell remains small.
import Workspace from './workspace';
createRoot(document.getElementById('root')).render(<App/>);
