import { useEffect, useRef, useState } from 'react';
import { Check, ArrowRight } from 'lucide-react';
import { api } from './api';
import { startVisiblePolling } from './polling';
import type { IdentityState, SecureHistoryProvider } from './history';

type Installation = { state: string; configured: boolean; reachable: boolean; url: string; managed?: boolean };
type Progress = { stage: string; completed: string[]; realm?: string; email?: string; allow_registration?: boolean;
  error?: string; message?: string; pending?: { id: string; actionType: string; entityType: string; blocked?: boolean }[] };
type Session = { unlocked: boolean; configured?: boolean; csrf?: string; busy?: boolean; progress?: Progress };
const steps = [ ['details', 'Your installation'], ['realm', 'Create your realm'], ['license', 'Activate Tide'],
  ['configure', 'Prepare secure history'], ['link', 'Connect your Tide account'], ['admin', 'Confirm administrator'], ['verify', 'Finish setup'] ];
const stageCopy: Record<string, string> = {
  realm: 'Creating a separate realm for Redacted.', license: 'Activating the licence and Tide protection.',
  configure: 'Preparing login, personal encryption permissions and Redacted branding.',
  link: 'Connect your Tide account to manage this installation. Complete the Tide window; this page will continue automatically.',
  admin: 'Confirming your account as this realm’s administrator.', verify: 'Checking the saved configuration.',
};
function Command({ children }: { children: string }) {
  const [copied, setCopied] = useState(false);
  return <div className="setup-command"><code>{children}</code><button type="button" className="text-button" onClick={() => {
    void navigator.clipboard.writeText(children).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); }).catch(() => {});
  }}>{copied ? 'Copied' : 'Copy'}</button></div>;
}
export function TideSetup({ identity, provider }: { identity: IdentityState; provider: SecureHistoryProvider }) {
  const [installation, setInstallation] = useState<Installation | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [realm, setRealm] = useState('redacted');
  const [email, setEmail] = useState('');
  const [registration, setRegistration] = useState(true);
  const [terms, setTerms] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const feedback = useRef<HTMLDivElement>(null);
  const current = useRef(session); current.current = session;
  const actionBusy = useRef(false);
  const automaticCheck = useRef<Promise<unknown> | null>(null);
  const reloadOnReady = useRef(false);
  const progress = session?.progress;
  async function post<T>(path: string, body: unknown = {}) {
    return api<T>('tide/setup/v2/' + path, { method: 'POST', headers: {
      'Content-Type': 'application/json', 'X-Setup-CSRF': current.current?.csrf || '' }, body: JSON.stringify(body) });
  }
  async function refresh() {
    const next = await api<Session>('tide/setup/v2/session');
    setSession(next);
    if (next.configured && reloadOnReady.current) window.location.reload();
    if (next.unlocked) reloadOnReady.current = true;
    return next;
  }
  useEffect(() => {
    let stop = () => {}; let live = true;
    // A setup link opened in this same tab changes only the fragment; React
    // does not remount. Reload to exchange it and read saved server progress.
    const followSetupLink = () => {
      if (new URLSearchParams(window.location.hash.slice(1)).has('setup')) window.location.reload();
    };
    window.addEventListener('hashchange', followSetupLink);
    const init = async () => {
      const fragment = new URLSearchParams(window.location.hash.slice(1));
      const token = fragment.get('setup');
      if (token) {
        // Consume the browser handoff from the URL fragment, then erase it before
        // any network navigation. It never enters HTTP access logs or storage.
        window.history.replaceState(null, '', window.location.pathname + window.location.search);
        try { await api('tide/setup/v2/exchange', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token }) }); }
        catch (e) { if (live) setError((e as Error).message); }
      } else if (fragment.has('code') || fragment.has('error') || new URLSearchParams(window.location.search).has('code')) {
        try { const { resumeSetupLogin } = await import('./tideSetupApproval'); await resumeSetupLogin(); }
        catch { if (live) setError('Tide sign-in did not finish. Try the approval button again.'); }
      }
      if (!live) return;
      let statusAt = 0;
      stop = startVisiblePolling(async () => {
        try {
          if (actionBusy.current) return;
          if (Date.now() - statusAt > 15000) { const status = await api<Installation>('tide/status'); if (live) setInstallation(status); statusAt = Date.now(); }
          if (!live) return;
          const next = await refresh();
          if ((next.progress?.stage === 'link' || next.progress?.pending?.length) && !next.busy && !actionBusy.current && !next.progress?.error) {
            current.current = next;
            const check = post('continue');
            automaticCheck.current = check;
            try {
              await check;
              if (live) await refresh();
            } finally {
              if (automaticCheck.current === check) automaticCheck.current = null;
            }
          }
        } catch { if (live) setError('Could not reach Redacted. Your setup progress is saved; reconnect to continue.'); }
      }, () => current.current?.busy ? 2000 : current.current?.unlocked ? 5000 : 30000);
    };
    void init();
    return () => { live = false; stop(); window.removeEventListener('hashchange', followSetupLink); };
  }, []);
  useEffect(() => { if (error || message || progress?.error) feedback.current?.scrollIntoView({ block: 'nearest' }); }, [error, message, progress?.error]);
  async function act(run: () => Promise<void>) {
    if (actionBusy.current) return;
    actionBusy.current = true; setBusy(true); setError(''); setMessage('');
    try {
      // A click takes priority over the next poll, and waits for an already
      // running check so it cannot collide with the backend's setup lock.
      await automaticCheck.current?.catch(() => {});
      await run(); await refresh();
    }
    catch (e) { setError((e as Error).message); }
    finally { actionBusy.current = false; setBusy(false); }
  }
  const configured = installation?.configured || session?.configured;
  const working = busy || session?.busy;
  return <section className="tide-setup" aria-label="Set up secure history">
    {configured ? <>
      <h2>Secure history is configured</h2>
      <p role="status">{installation?.reachable ? 'TideCloak is running. Sign in to keep your files.' : 'TideCloak is stopped or unreachable. Your encrypted history is retained.'}</p>
      {!installation?.reachable && (installation?.managed ? <Command>python3 scripts/tidecloak.py start</Command> :
        <p className="setup-note">Start the TideCloak server connected to this installation, then reconnect here.</p>)}
      {identity.status === 'signed-out' && <button className="primary" onClick={() => void act(() => provider.signIn())}>Sign in <ArrowRight/></button>}
      {identity.status === 'authenticated' && provider.testProtection && <button className="settings-button" disabled={busy} onClick={() => void act(async () => {
        await provider.testProtection!(new AbortController().signal); setMessage('Encryption and decryption verified in your browser.');
      })}>{busy ? 'Checking encryption…' : 'Test encrypted history'}</button>}
      {identity.status === 'error' && <button className="settings-button" onClick={() => window.location.reload()}>Reconnect</button>}
    </> : !session ? <div className="setup-loading" role="status"><span className="decrypt-skeleton"/> Checking setup…</div> : !session.unlocked ? <>
      <h2>Start here</h2>
      <p>Run this from your Redacted project folder. It {installation?.reachable && !installation.managed ? 'connects to your running TideCloak and' : 'starts TideCloak and'} opens this guide with setup already unlocked.</p>
      <Command>{installation?.reachable && !installation.managed ? 'python3 scripts/tidecloak.py connect' : 'python3 scripts/tidecloak.py start'}</Command>
      <p className="setup-note">Returning to an unfinished setup? The same command restores access to your saved progress.</p>
      <details><summary>Already running TideCloak?</summary><p>Connect using its owner credentials in your terminal. Its existing realms stay separate.</p>
        <Command>python3 scripts/tidecloak.py connect</Command>
      </details>
    </> : <>
      <ol className="setup-checklist" aria-label="Setup progress">{steps.map(([id, title]) => {
        const done = progress?.completed.includes(id);
        return <li key={id} aria-current={progress?.stage === id ? 'step' : undefined} className={done ? 'done' : ''}>
          <span className="setup-step-marker">{done ? <Check size={14}/> : steps.findIndex(s => s[0] === id) + 1}</span><span>{title}</span>
          {progress?.stage === id && working && <span className="setup-step-loader" aria-label="Working"/>}
        </li>;
      })}</ol>
      {(!progress || progress.stage === 'details') ? <form className="setup-form" onSubmit={event => {
        event.preventDefault(); void act(async () => { await post('begin', { realm, email, allow_registration: registration, accept_terms: terms }); });
      }}>
        <h2>Your installation</h2>
        <label>Realm name<input value={realm} onChange={e => setRealm(e.target.value)} required pattern="[A-Za-z0-9_-]+" maxLength={80}/></label>
        <p className="setup-note">A separate space for Redacted’s accounts. Choose a new name; existing realms won’t be changed.</p>
        <label>Email for Tide licensing<input type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} required maxLength={254}/></label>
        <label className="setup-check"><input type="checkbox" checked={registration} onChange={e => setRegistration(e.target.checked)}/> Allow others to sign up for their own encrypted history</label>
        <label className="setup-check"><input type="checkbox" checked={terms} onChange={e => setTerms(e.target.checked)} required/><span>I accept <a href="https://tide.org/legal" target="_blank" rel="noopener noreferrer">Tide’s terms</a> for this installation.</span></label>
        <button className="primary" disabled={working || !terms}>{working ? 'Preparing…' : 'Enable secure history'} <ArrowRight/></button>
      </form> : <div className="setup-current">
        <h2>{steps.find(s => s[0] === progress.stage)?.[1] || 'Secure history'}</h2>
        <p role="status">{stageCopy[progress.stage]}</p>
        {progress.stage === 'link' && <button className="primary" disabled={working} onClick={() => {
          const popup = window.open('about:blank', 'redacted-tide-link', 'popup,width=580,height=760');
          if (!popup) { setError('Allow pop-ups for Redacted, then try again.'); return; }
          void act(async () => { try { const result = await post<{ url: string }>('link'); popup.location.href = result.url; } catch (e) { popup.close(); throw e; } });
        }}>Connect my Tide account <ArrowRight/></button>}
        {!!progress.pending?.length && <>
          <p>{progress.pending.length} change{progress.pending.length === 1 ? ' needs' : 's need'} your approval.</p>
          <ul>{progress.pending.map(p => <li key={p.id}>{p.actionType.replaceAll('_', ' ').toLowerCase()} ({p.entityType.toLowerCase()}){p.blocked ? ' — waiting on an earlier change' : ''}</li>)}</ul>
          <button className="primary" disabled={working} onClick={() => void act(async () => {
            const { approveSetupRequests } = await import('./tideSetupApproval');
            if (await approveSetupRequests(progress.pending!.map(p => p.id), post)) await post('continue');
          })}>Review and approve with Tide <ArrowRight/></button>
        </>}
        {!working && (progress.error || (progress.stage !== 'link' && !progress.pending?.length)) && <button className="settings-button" onClick={() => void act(async () => { await post('continue'); })}>{progress.error ? 'Retry this step' : 'Continue setup'}</button>}
        <p className="setup-note">Progress is saved. You can return to this page if you close it.</p>
      </div>}
    </>}
    <div ref={feedback} aria-live="polite">
      {(error || progress?.error) && <p role="alert" className="notice">{error || progress?.error}</p>}
      {message && <p role="status" className="notice">{message}</p>}
    </div>
    <p className="setup-note">Your app and files stay on this machine. Authentication and encryption use Tide’s network.</p>
  </section>;
}
