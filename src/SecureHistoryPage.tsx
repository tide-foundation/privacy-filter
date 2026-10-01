import { useState } from 'react';
import type { IdentityState, SecureHistoryProvider } from './history';

export function SecureHistoryPage({ identity, provider, available, navigate }: {
  identity: IdentityState; provider: SecureHistoryProvider; available: boolean; navigate: (path: string) => void;
}) {
  const [error, setError] = useState('');
  const canSignIn = available && identity.status === 'signed-out';
  return <main className="history-information">
    <button className="text-button back-link" onClick={() => navigate('/')}>← Back to redacting</button>
    <h1>Secure your history</h1>
    <p className="information-lead">Keep your redactions and return to them later.</p>
    <ul className="history-benefits">
      <li>Retain previous redactions and their documents.</li>
      <li>Review detections and reveal original values when authorised.</li>
      <li>Recover originals or regenerate results where supported.</li>
      <li>Protect retained documents and sensitive values at rest.</li>
    </ul>
    <p>Guest redaction and secure history are both free. You can keep redacting and downloading without an account.</p>
    <section className="history-security"><h2>How history will be protected</h2>
      <p>Secure history will use TideCloak and Tide to sign you in and encrypt retained documents and detection details. Original values will be revealed only after authorised decryption in your browser.</p>
      <p>When you reprocess a document, the browser sends its decrypted contents to this local server temporarily. Protection at rest does not mean the server cannot see a document while processing it.</p>
    </section>
    {identity.status === 'unavailable' || !available ? <p className="notice" role="status">Secure history is not configured. Signing in, saving history and revealing protected values are unavailable on this installation.</p> : null}
    {error && <p className="notice" role="alert">{error}</p>}
    <button className="primary history-sign-in" disabled={!canSignIn} onClick={() => { setError(''); void provider.signIn().catch(() => setError('Sign-in could not be started. Please try again.')); }}>Sign in to keep history</button>
  </main>;
}
