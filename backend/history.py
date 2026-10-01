"""Owner-scoped metadata and opaque protected artifacts; never decrypts payloads."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import time
from typing import Literal
from uuid import UUID, uuid4
import shutil

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from backend.auth import VerifiedOwner
from backend.documents import LABELS

KINDS = frozenset({'source', 'manifest', 'output_pdf', 'output_docx', 'output_txt'})
MAX_ARTIFACT = 64 * 1024 * 1024
MAX_DOCUMENT = 192 * 1024 * 1024
MAX_OWNER_DOCUMENTS = 100
DRAFT_TTL = 15 * 60
SCHEMA_VERSION = 1


class HistoryMetadata(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_type: Literal['pdf', 'docx']
    mode: Literal['redact', 'placeholder', 'synthetic']
    sensitivity: int = Field(default=50, ge=0, le=100, multiple_of=5, strict=True)
    counts: dict[str, StrictInt] = Field(default_factory=dict)
    layout_preserved: bool = Field(strict=True)
    warning_codes: list[Literal['images_unscanned', 'layout_fallback', 'ocr_unavailable']] = Field(default_factory=list, max_length=3)
    protection_version: Literal[1] = 1

    @field_validator('counts')
    @classmethod
    def safe_counts(cls, value):
        if not set(value).issubset(LABELS) or any(type(count) is not int or count < 0 or count > 200_000 for count in value.values()):
            raise ValueError('Invalid detection counts.')
        return value


def valid_identifier(identifier):
    try:
        return str(UUID(identifier)) == identifier
    except (ValueError, TypeError):
        return False


class HistoryStore:
    def __init__(self, root: Path, *, clock=time.time):
        self.root, self.path, self.clock = root, root / 'documents.sqlite3', clock
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connection() as conn:
            version = conn.execute('PRAGMA user_version').fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError('This history database requires a newer application version.')
            # Legacy records have no owner and must never be assigned to a new user.
            legacy = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='documents'").fetchone()
            if legacy:
                conn.execute('DROP TABLE documents')
            conn.execute('CREATE TABLE IF NOT EXISTS history_documents ('
                         'id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, created REAL NOT NULL, '
                         "status TEXT NOT NULL CHECK(status IN ('draft','complete')), expires REAL, "
                         'metadata TEXT NOT NULL, protection_version INTEGER NOT NULL)')
            conn.execute('CREATE INDEX IF NOT EXISTS history_owner ON history_documents(owner_id, created)')
            conn.execute('CREATE TABLE IF NOT EXISTS history_artifacts ('
                         'document_id TEXT NOT NULL REFERENCES history_documents(id) ON DELETE CASCADE, '
                         'kind TEXT NOT NULL, payload BLOB NOT NULL, PRIMARY KEY(document_id, kind))')
            conn.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
        self.path.chmod(0o600)
        # Legacy UUID output folders are a reserved namespace. Sweep every start
        # so interruption after the schema transaction cannot strand old plaintext.
        for path in root.iterdir():
            if valid_identifier(path.name):
                if path.is_symlink():
                    path.unlink()
                elif path.is_dir():
                    shutil.rmtree(path)
        self.cleanup()

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA secure_delete=ON')
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def owner(owner):
        if not isinstance(owner, VerifiedOwner):
            raise TypeError('History operations require a verified owner.')
        return owner.owner_id

    def cleanup(self):
        with self.connection() as conn:
            conn.execute("DELETE FROM history_documents WHERE status='draft' AND expires<=?", (self.clock(),))

    def _record(self, conn, owner, identifier):
        if not valid_identifier(identifier):
            raise HTTPException(404, 'History document not found.')
        row = conn.execute('SELECT * FROM history_documents WHERE owner_id=? AND id=?', (self.owner(owner), identifier)).fetchone()
        if row is None or (row['status'] == 'draft' and row['expires'] <= self.clock()):
            raise HTTPException(404, 'History document not found.')
        return row

    @staticmethod
    def public(row):
        import json
        return {'id': row['id'], 'created': datetime.fromtimestamp(row['created'], timezone.utc).isoformat(),
                'status': row['status'], 'protection_version': row['protection_version'],
                **json.loads(row['metadata'])}

    def create(self, owner, metadata):
        owner_id = self.owner(owner)
        self.cleanup()
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            count = conn.execute('SELECT COUNT(*) FROM history_documents WHERE owner_id=?', (owner_id,)).fetchone()[0]
            if count >= MAX_OWNER_DOCUMENTS:
                raise HTTPException(429, 'History storage is full. Delete a document before saving another.')
            identifier, now = str(uuid4()), self.clock()
            conn.execute('INSERT INTO history_documents VALUES (?,?,?,?,?,?,?)',
                         (identifier, owner_id, now, 'draft', now + DRAFT_TTL, metadata.model_dump_json(), 1))
            return self.public(self._record(conn, owner, identifier))

    def listing(self, owner):
        owner_id = self.owner(owner)
        self.cleanup()
        with self.connection() as conn:
            return [self.public(row) for row in conn.execute(
                "SELECT * FROM history_documents WHERE owner_id=? AND status='complete' ORDER BY created DESC", (owner_id,))]

    def get(self, owner, identifier):
        with self.connection() as conn:
            return self.public(self._record(conn, owner, identifier))

    def put(self, owner, identifier, kind, payload):
        if kind not in KINDS:
            raise HTTPException(400, 'Unsupported artifact kind.')
        if not payload or len(payload) > MAX_ARTIFACT:
            raise HTTPException(413, 'Protected artifact is empty or exceeds the storage limit.')
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = self._record(conn, owner, identifier)
            if row['status'] != 'draft':
                raise HTTPException(409, 'Completed history is immutable. Create a new record.')
            size = conn.execute('SELECT COALESCE(SUM(length(payload)),0) FROM history_artifacts WHERE document_id=? AND kind<>?', (identifier, kind)).fetchone()[0]
            if size + len(payload) > MAX_DOCUMENT:
                raise HTTPException(413, 'Protected document exceeds the storage limit.')
            conn.execute('INSERT INTO history_artifacts VALUES (?,?,?) ON CONFLICT(document_id,kind) DO UPDATE SET payload=excluded.payload',
                         (identifier, kind, payload))

    def artifact(self, owner, identifier, kind):
        with self.connection() as conn:
            self._record(conn, owner, identifier)
            row = conn.execute('SELECT payload FROM history_artifacts WHERE document_id=? AND kind=?', (identifier, kind)).fetchone()
            if row is None:
                raise HTTPException(404, 'Protected artifact not found.')
            return row['payload']

    def commit(self, owner, identifier):
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            self._record(conn, owner, identifier)
            kinds = {row[0] for row in conn.execute('SELECT kind FROM history_artifacts WHERE document_id=?', (identifier,))}
            if kinds != KINDS:
                raise HTTPException(409, 'Upload all protected artifacts before saving history.')
            conn.execute("UPDATE history_documents SET status='complete', expires=NULL WHERE owner_id=? AND id=?", (self.owner(owner), identifier))
            return self.public(self._record(conn, owner, identifier))

    def delete(self, owner, identifier):
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            self._record(conn, owner, identifier)
            conn.execute('DELETE FROM history_documents WHERE owner_id=? AND id=?', (self.owner(owner), identifier))
