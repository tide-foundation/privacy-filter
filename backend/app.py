from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
from threading import Lock
from uuid import uuid4, UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from backend.documents import extract, transform, export_files

ROOT = Path(os.environ.get('PRIVACY_DATA_DIR', './data')).resolve()
LIMIT = 20 * 1024 * 1024
pool = ThreadPoolExecutor(max_workers=1)
slots = Lock()
active = 0
model = None


def db():
    conn = sqlite3.connect(ROOT / 'documents.sqlite3')
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA secure_delete=ON')
    return conn


@asynccontextmanager
async def lifespan(app):
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    with db() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, created TEXT, mode TEXT, status TEXT, counts TEXT, error TEXT, warning TEXT)')
        conn.execute("UPDATE documents SET status='failed', error='Processing was interrupted. Please upload again.' WHERE status IN ('queued','processing')")
        failed = conn.execute("SELECT id FROM documents WHERE status='failed'").fetchall()
    for row in failed:
        shutil.rmtree(ROOT / row['id'], ignore_errors=True)
    yield
    pool.shutdown(wait=True)


app = FastAPI(lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])


@app.middleware('http')
async def local_only(request: Request, call_next):
    origin = request.headers.get('origin')
    if origin and origin not in {'http://localhost:3000', 'http://127.0.0.1:3000'}:
        return JSONResponse({'detail': 'Origin not allowed.'}, status_code=403)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


def run_job(identifier, data, suffix, mode):
    global model, active
    try:
        with db() as conn:
            conn.execute("UPDATE documents SET status='processing' WHERE id=?", (identifier,))
        text = extract(data, suffix)
        del data
        if model is None:
            from opf import OPF
            model = OPF(device=os.environ.get('OPF_DEVICE', 'cpu'), output_mode='typed')
        result = model.redact(text)
        sanitized, counts = transform(result, mode)
        export_files(sanitized, ROOT / identifier)
        with db() as conn:
            conn.execute("UPDATE documents SET status='complete', counts=?, warning=? WHERE id=?",
                         (json.dumps(counts), result.warning, identifier))
    except Exception as exc:
        shutil.rmtree(ROOT / identifier, ignore_errors=True)
        # Parser/model exception strings can contain private input. Only expose our own validation messages.
        safe = str(exc) if isinstance(exc, ValueError) and exc.__traceback__ and _is_validation(exc) else 'Processing failed. Check that the model is installed, its checkpoint is available, and the document is readable.'
        with db() as conn:
            conn.execute("UPDATE documents SET status='failed', error=? WHERE id=?", (safe, identifier))
    finally:
        with slots:
            active -= 1


def _is_validation(exc):
    tb = exc.__traceback__
    while tb.tb_next:
        tb = tb.tb_next
    return tb.tb_frame.f_code.co_filename.endswith('/backend/documents.py')


@app.get('/health')
def health():
    return {'service': 'ready', 'model_installed': importlib.util.find_spec('opf') is not None,
            'model_loaded': model is not None and model._runtime is not None,
            'device': os.environ.get('OPF_DEVICE', 'cpu')}


@app.get('/documents')
def listing():
    with db() as conn:
        rows = conn.execute('SELECT * FROM documents ORDER BY created DESC').fetchall()
    return [dict(row) | {'counts': json.loads(row['counts'] or '{}')} for row in rows]


@app.post('/documents', status_code=202)
async def upload(request: Request):
    global active
    mode = request.query_params.get('mode', 'placeholder')
    suffix = request.query_params.get('type', '')
    if mode not in {'placeholder', 'synthetic'} or suffix not in {'.docx', '.pdf'}:
        raise HTTPException(400, 'Choose a PDF or DOCX and a supported replacement mode.')
    if importlib.util.find_spec('opf') is None:
        raise HTTPException(503, 'Install the local model with: .venv/bin/pip install -r backend/requirements-model.txt')
    with slots:
        if active >= 3:
            raise HTTPException(429, 'The local queue is full. Wait for a document to finish.')
        active += 1
    try:
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > LIMIT:
                raise HTTPException(413, 'The upload limit is 20 MB.')
            data.extend(chunk)
        if not data:
            raise HTTPException(400, 'The file is empty.')
        identifier = str(uuid4())
        with db() as conn:
            conn.execute('INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)',
                         (identifier, datetime.now(timezone.utc).isoformat(), mode, 'queued', '{}', None, None))
        pool.submit(run_job, identifier, bytes(data), suffix, mode)
        return {'id': identifier}
    except BaseException:
        with slots:
            active -= 1
        raise


def get_doc(identifier):
    try:
        if str(UUID(identifier)) != identifier:
            raise ValueError()
    except ValueError:
        raise HTTPException(404, 'Document not found.') from None
    with db() as conn:
        row = conn.execute('SELECT * FROM documents WHERE id=?', (identifier,)).fetchone()
    if row is None:
        raise HTTPException(404, 'Document not found.')
    return row


@app.get('/documents/{identifier}/preview')
def preview(identifier: str):
    row = get_doc(identifier)
    if row['status'] != 'complete':
        raise HTTPException(409, 'This document is not ready.')
    return {'text': (ROOT / identifier / 'sanitized.txt').read_text(encoding='utf-8')}


@app.get('/documents/{identifier}/download/{extension}')
def download(identifier: str, extension: str):
    row = get_doc(identifier)
    if extension not in {'pdf', 'docx', 'txt'} or row['status'] != 'complete':
        raise HTTPException(404, 'Output not found.')
    return FileResponse(ROOT / identifier / f'sanitized.{extension}', filename=f'sanitized-{identifier[:8]}.{extension}')


@app.delete('/documents/{identifier}')
def delete(identifier: str):
    row = get_doc(identifier)
    if row['status'] in {'queued', 'processing'}:
        raise HTTPException(409, 'Wait for processing to finish before deleting.')
    shutil.rmtree(ROOT / identifier, ignore_errors=False) if (ROOT / identifier).exists() else None
    with db() as conn:
        conn.execute('DELETE FROM documents WHERE id=?', (identifier,))
    return {'deleted': True}
