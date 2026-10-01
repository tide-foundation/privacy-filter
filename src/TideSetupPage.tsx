import { TideSetup } from './TideSetup';
import type { IdentityState, SecureHistoryProvider } from './history';

export function TideSetupPage({ identity, provider, navigate }: {
  identity: IdentityState; provider: SecureHistoryProvider; navigate: (path: string) => void;
}) {
  return <main className="history-information">
    <button className="text-button back-link" onClick={() => navigate('/secure-history')}>← About secure history</button>
    <h1>Set up TideCloak</h1>
    <p className="information-lead">A guide for the person running this Redacted installation.</p>
    <TideSetup identity={identity} provider={provider}/>
    {identity.status === 'authenticated' && <p><button className="text-button" onClick={() => navigate('/')}>Back to your files →</button></p>}
  </main>;
}
