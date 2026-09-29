'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowDownToLine, ArrowRight, Check, FileText, LoaderCircle, Trash2, Upload, X } from 'lucide-react';
type Doc = { source_type?: string; id: string; created: string; mode: string; status: string; counts: Record<string, number>; error?: string; warning?: string };
type Health = { model_installed: boolean; model_loaded: boolean; device: string };
const labels: Record<string, string> = { private_person: 'Names', private_address: 'Addresses', private_email: 'Emails', private_phone: 'Phone numbers', private_date: 'Dates', private_url: 'URLs', account_number: 'Accounts', secret: 'Secrets' };
async function api(path: string, init?: RequestInit) {
  const response = await fetch(`/api/service/${path}`, { ...init, cache: 'no-store' });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'The request could not be completed.');
  return data;
}
export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState('placeholder');
  const [docs, setDocs] = useState<Doc[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState('');
  const [connection, setConnection] = useState('');
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [preview, setPreview] = useState<{ id: string; text: string } | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const input = useRef<HTMLInputElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const refresh = useCallback(async () => {
    try {
      const [items, state] = await Promise.all([api('documents'), api('health')]);
      setDocs(items); setHealth(state); setConnection('');
    } catch (e) { setConnection((e as Error).message); setHealth(null); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void refresh(); const timer = setInterval(refresh, 3000); return () => clearInterval(timer); }, [refresh]);
  useEffect(() => { if (preview) dialog.current?.showModal(); else dialog.current?.close(); }, [preview]);
  function choose(next: File | undefined) {
    if (!next) return;
    if (!/\.(docx|pdf)$/i.test(next.name)) { setError('Choose a PDF or DOCX. Convert legacy .doc files to .docx first.'); return; }
    if (next.size > 20 * 1024 * 1024) { setError('Choose a file smaller than 20 MB.'); return; }
    if (!next.size) { setError('This file is empty.'); return; }
    setFile(next); setError('');
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault(); if (!file) return;
    setBusy(true); setError('');
    try {
      const suffix = '.' + file.name.split('.').pop()!.toLowerCase();
      await api(`documents?mode=${mode}&type=${suffix}`, { method: 'POST', body: file });
      setFile(null); if (input.current) input.current.value = ''; await refresh();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function remove(id: string) {
    setDeleting(id); setError('');
    try { await api(`documents/${id}`, { method: 'DELETE' }); if (preview?.id === id) setPreview(null); await refresh(); }
    catch (e) { setError((e as Error).message); } finally { setDeleting(null); }
  }
  async function openPreview(id: string) {
    try { setPreview({ id, ...(await api(`documents/${id}/preview`)) }); } catch (e) { setError((e as Error).message); }
  }
  const total = docs.filter(d => d.status === 'complete').length;
  return <>
    <header className="topbar">
      <a className="brand" href="/" aria-label="Tide home"><img src="/tide-logo.svg" alt="Tide" width="92" height="48" /></a>
    </header>
    <main>
      <h1>Cleanse me!</h1>
      <form onSubmit={submit}>
        <input ref={input} id="document" type="file" accept=".pdf,.docx" onChange={e => choose(e.target.files?.[0])} className="file-input" disabled={busy}/>
        <label htmlFor="document" className={`dropzone ${drag ? 'dragging' : ''} ${file ? 'selected' : ''}`} onDragOver={e => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={e => { e.preventDefault(); setDrag(false); if (!busy) choose(e.dataTransfer.files[0]); }}>
          {file ? <FileText size={26}/> : <Upload size={26}/>}
          <strong>{file ? file.name : 'Choose a file'}</strong>
          <small>{file ? `${(file.size / 1024).toFixed(0)} KB` : 'PDF / DOCX · 20 MB max'}</small>
        </label>
        <div className="form-actions">
          <fieldset aria-label="Replacement mode">
            {[['placeholder', 'Placeholders'], ['synthetic', 'Synthetic data']].map(([value, title]) => (
              <label key={value} className={`mode-option ${mode === value ? 'active' : ''}`}>
                <input type="radio" name="mode" value={value} checked={mode === value} onChange={() => setMode(value)} />
                <span className="radio-mark">{mode === value && <Check size={12}/>}</span>
                {title}
              </label>
            ))}
          </fieldset>
          <button className="primary" type="submit" disabled={!file || busy || !health?.model_installed}>
            {busy ? <><LoaderCircle className="spin" size={17}/> Uploading…</> : <>Cleanse <ArrowRight size={17}/></>}
          </button>
        </div>
      </form>
      {connection && <div className="notice" role="status">Service unavailable.</div>}
      {health && !health.model_installed && <div className="notice" role="status">Model unavailable. See the README for setup.</div>}
      {error && <div className="notice error" role="alert">{error}<button aria-label="Dismiss error" onClick={() => setError('')}><X size={17}/></button></div>}
      <section className="library"><div className="library-heading"><h2>Files <span className="count">{total}</span></h2></div>
        {loading ? <div className="empty" role="status"><LoaderCircle className="spin" size={18}/><span>Loading…</span></div> : docs.length === 0 ? <div className="empty">No files yet.</div> : <div className="document-list">{docs.map(doc => <article className="document-row" key={doc.id}><div className="doc-icon"><FileText size={22}/></div><div className="doc-info"><h3>Document {doc.id.slice(0, 8)} {['queued', 'processing'].includes(doc.status) && (
                  <span className="processing-indicator" role="status" title={doc.status === 'queued' ? 'Queued' : 'Processing'}>
                    <span className="processing-ring" aria-hidden="true" />
                    <span className="sr-only">{doc.status === 'queued' ? 'Queued' : 'Processing'}</span>
                  </span>
                )}
                {doc.status === 'failed' && <span className="status failed">Failed</span>}</h3><p>{new Date(doc.created).toLocaleString()} <span>·</span> {doc.mode === 'placeholder' ? 'Placeholders' : 'Synthetic data'}</p>{doc.status === 'complete' && <div className="counts">{Object.entries(doc.counts).length ? Object.entries(doc.counts).map(([key, value]) => <span key={key}>{value} {labels[key]?.toLowerCase() || key}</span>) : <span>No detections</span>}</div>}{doc.error && <p className="doc-error">{doc.error}</p>}{doc.warning && <p className="doc-error">{doc.warning}</p>}</div><div className="doc-actions">{doc.status === 'complete' && <><button className="text-button" onClick={() => openPreview(doc.id)}>Preview</button><div className="downloads">{(doc.source_type === 'pdf' ? ['pdf', 'docx', 'txt'] : ['docx', 'pdf', 'txt']).map(ext => <a key={ext} title={doc.source_type === ext ? "Original layout" : "Rebuilt text"} href={`/api/service/documents/${doc.id}/download/${ext}`} aria-label={`Download ${ext.toUpperCase()} for document ${doc.id.slice(0,8)}`}><ArrowDownToLine size={13}/>{ext.toUpperCase()}</a>)}</div></>}<button className="delete" onClick={() => remove(doc.id)} disabled={['queued', 'processing'].includes(doc.status) || deleting === doc.id} aria-label={`Delete document ${doc.id.slice(0, 8)} and all its output files`} title="Delete document and all output files">{deleting === doc.id ? <LoaderCircle className="spin" size={17}/> : <Trash2 size={17}/>}</button></div></article>)}</div>}
      </section>
    </main><dialog ref={dialog} onCancel={() => setPreview(null)} onClick={e => { if (e.target === e.currentTarget) setPreview(null); }}><div className="preview-header"><h2>Preview</h2><button aria-label="Close preview" onClick={() => setPreview(null)}><X/></button></div><pre>{preview?.text}</pre></dialog>
  </>;
}
