import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { ArrowDownToLine, LoaderCircle, Trash2 } from 'lucide-react';
import type { DetectionReview, DocumentResult, OutputFormat, RevealedDetection } from './types';
import { modeLabels } from './types';
import { ReviewPanel } from './ReviewPanel';

export type IdentityState =
  | { status: 'unavailable'; reason: string }
  | { status: 'signed-out' | 'loading' | 'error' }
  | { status: 'authenticated'; ownerKey: string };
export type { RevealedDetection } from './types';
export type HistoryRecord = DocumentResult;
export type TransientHistoryInput = {
  source: Blob;
  manifest: Blob;
  outputs: Record<OutputFormat, Blob>;
  // Only safe metadata may enter the durable record. Protect filename in the manifest.
  metadata: Omit<DocumentResult, 'filename'>;
  filename?: string;
};
export type ReprocessInput = { source: Blob; mode: DocumentResult['mode']; sensitivity: number };


// Implement only through the final, verified authentication/protection integration.
// The adapter owns authorised API access and decryption; tokens are not component props.
export interface SecureHistoryProvider {
  getSnapshot(): IdentityState;
  subscribe(listener: () => void): () => void;
  signIn(): Promise<void>;
  signOut(): Promise<void>;
  // These receive/return transient plaintext in memory. The verified adapter
  // must protect every durable artifact before storage, including outputs.
  save(input: TransientHistoryInput, signal: AbortSignal): Promise<HistoryRecord>;
  recoverOriginal(id: string, signal: AbortSignal): Promise<Blob>;
  reprocessSource(id: string, signal: AbortSignal): Promise<ReprocessInput>;
  list(signal: AbortSignal): Promise<HistoryRecord[]>;
  remove(id: string, signal: AbortSignal): Promise<void>;
  review(id: string, signal: AbortSignal): Promise<DetectionReview>;
  reveal(id: string, signal: AbortSignal): Promise<RevealedDetection[]>;
  download(id: string, format: OutputFormat, signal: AbortSignal): Promise<Blob>;
}

const unavailable: IdentityState = Object.freeze({ status: 'unavailable', reason: 'Secure history is not configured.' });
const rejectUnavailable = async (): Promise<never> => { throw new Error('Secure history is not configured.'); };
export const unavailableHistoryProvider: SecureHistoryProvider = Object.freeze({
  getSnapshot: () => unavailable,
  subscribe: () => () => {},
  signIn: rejectUnavailable, signOut: rejectUnavailable, list: rejectUnavailable,
  remove: rejectUnavailable, review: rejectUnavailable, reveal: rejectUnavailable, download: rejectUnavailable,
  save: rejectUnavailable, recoverOriginal: rejectUnavailable, reprocessSource: rejectUnavailable,
});
export function useIdentity(provider: SecureHistoryProvider) {
  return useSyncExternalStore(provider.subscribe, provider.getSnapshot, provider.getSnapshot);
}

// This component can receive an authorised provider in the final integration, or
// an isolated test fixture. Production defaults never manufacture an identity.
export function HistoryPanel({ provider, identity }: { provider: SecureHistoryProvider; identity: IdentityState }) {
  const [records, setRecords] = useState<HistoryRecord[]>([]);
  const [selected, setSelected] = useState<{ record: HistoryRecord; review: DetectionReview } | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const activeAction = useRef<AbortController | null>(null);
  const owner = identity.status === 'authenticated' ? identity.ownerKey : null;
  useEffect(() => {
    const controller = new AbortController();
    setRecords([]); setSelected(null); setError('');
    if (owner) {
      setBusy(true);
      provider.list(controller.signal).then(items => { if (!controller.signal.aborted) setRecords(items); })
        .catch(() => { if (!controller.signal.aborted) setError('Could not load secure history.'); })
        .finally(() => { if (!controller.signal.aborted) setBusy(false); });
    }
    return () => controller.abort();
  }, [provider, owner, revision]);
  useEffect(() => {
    const hide = () => { if (document.visibilityState === 'hidden') { activeAction.current?.abort(); } };
    document.addEventListener('visibilitychange', hide);
    return () => document.removeEventListener('visibilitychange', hide);
  }, [selected]);
  const [action, setAction] = useState<{ controller: AbortController; run: () => Promise<void> } | null>(null);
  useEffect(() => {
    if (!action) return;
    action.run();
    return () => action.controller.abort();
  }, [action]);
  useEffect(() => () => { action?.controller.abort(); }, [action, owner]);
  function startAction(run: (signal: AbortSignal) => Promise<void>) {
    activeAction.current?.abort();
    const controller = new AbortController();
    activeAction.current = controller;
    setAction({ controller, run: async () => {
      try { await run(controller.signal); }
      catch { if (!controller.signal.aborted) setError('The secure history action could not be completed.'); }
    } });
  }
  if (!owner) return null;
  return <section className="library" aria-label="Secure history">
    <div className="library-heading"><h2>Your history</h2></div>
    {error && <p role="alert" className="notice">{error}</p>}
    {busy ? <p className="empty"><LoaderCircle className="spin" size={18}/>Loading…</p> : records.length === 0 ? <p className="empty">No saved redactions.</p> : records.map(record => <article className="document-row" key={record.id}>
      <div className="doc-info"><h3><span className="document-name" title={record.filename || undefined}><span className="filename-text">{record.filename || `Document ${record.id.slice(0, 8)}`}</span></span><span className="mode-pill">{modeLabels[record.mode][1]}</span></h3><p>{new Date(record.created).toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' })}</p></div>
      <div className="doc-actions">
        <button className="text-button" onClick={() => { setSelected(null); startAction(async signal => { const review = await provider.review(record.id, signal); if (!signal.aborted) setSelected({ record, review }); }); }}>Review detections</button>
        <div className="downloads">{(['pdf', 'docx', 'txt'] as OutputFormat[]).map(format => <button key={format} onClick={() => startAction(async signal => {
          const blob = await provider.download(record.id, format, signal);
          if (signal.aborted) return;
          const url = URL.createObjectURL(blob);
          const link = document.createElement('a'); link.href = url; link.download = `sanitized-${record.id.slice(0, 8)}.${format}`;
          link.click(); setTimeout(() => URL.revokeObjectURL(url), 0);
        })}><ArrowDownToLine size={13}/>{format.toUpperCase()}</button>)}</div>
        <button className="delete" aria-label="Delete saved document" onClick={() => {
          if (!window.confirm('Are you sure you want to trash this file?')) return;
          startAction(async signal => { await provider.remove(record.id, signal); if (!signal.aborted) setRevision(value => value + 1); });
        }}><Trash2 size={17}/></button>
      </div>
    </article>)}
    {selected && <ReviewPanel key={selected.record.id} review={selected.review} onClose={() => { action?.controller.abort(); setSelected(null); }}
      onReveal={signal => provider.reveal(selected.record.id, signal)}/>}
  </section>;
}
