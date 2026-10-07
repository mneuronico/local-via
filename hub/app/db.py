import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS classes (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, code TEXT NOT NULL UNIQUE,
    expires_at REAL, max_uses INTEGER, uses INTEGER NOT NULL DEFAULT 0,
    revoked INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE, display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK (role IN ('student','admin')),
    class_id TEXT REFERENCES classes(id) ON DELETE SET NULL, disabled INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL, last_login_at REAL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at REAL NOT NULL, expires_at REAL NOT NULL, ip TEXT
);
CREATE TABLE IF NOT EXISTS workers (
    id TEXT PRIMARY KEY, token_hash TEXT NOT NULL, disabled INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL, last_seen_at REAL, ip TEXT, backend TEXT, version TEXT,
    loaded_model TEXT, gpu_json TEXT, installed_json TEXT, current_job_id TEXT
);
CREATE TABLE IF NOT EXISTS uploads (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL, media_type TEXT NOT NULL, kind TEXT NOT NULL, expected_size INTEGER NOT NULL,
    received INTEGER NOT NULL DEFAULT 0, path TEXT NOT NULL, complete INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    model TEXT NOT NULL, task TEXT NOT NULL, prompt TEXT NOT NULL, inputs_json TEXT NOT NULL,
    parameters_json TEXT NOT NULL, status TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0,
    phase TEXT, error TEXT, worker_id TEXT, attempts INTEGER NOT NULL DEFAULT 0,
    cancel_requested INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL, claimed_at REAL,
    finished_at REAL, lease_expires_at REAL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL, name TEXT NOT NULL, media_type TEXT NOT NULL, size INTEGER NOT NULL,
    path TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, actor TEXT, action TEXT NOT NULL,
    detail TEXT, ip TEXT
);
CREATE TABLE IF NOT EXISTS settings_kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_artifacts_job ON artifacts(job_id);
CREATE INDEX IF NOT EXISTS idx_uploads_user ON uploads(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
"""


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.connection.executescript(SCHEMA)

    def execute(self, sql: str, values: tuple[Any, ...] = ()) -> int:
        with self.lock:
            return self.connection.execute(sql, values).rowcount

    def one(self, sql: str, values: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self.lock:
            row = self.connection.execute(sql, values).fetchone()
            return dict(row) if row else None

    def all(self, sql: str, values: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.lock:
            return [dict(row) for row in self.connection.execute(sql, values).fetchall()]

    def transaction(self):
        return _Transaction(self)

    def audit(self, action: str, actor: str | None = None, detail: str | None = None, ip: str | None = None) -> None:
        self.execute("INSERT INTO audit (at, actor, action, detail, ip) VALUES (?,?,?,?,?)", (time.time(), actor, action, detail, ip))

    def close(self) -> None:
        with self.lock:
            self.connection.close()


class _Transaction:
    """Serializes a multi-statement read/modify/write under the process lock and SQLite's write lock."""

    def __init__(self, db: Database):
        self.db = db

    def __enter__(self) -> sqlite3.Connection:
        self.db.lock.acquire()
        self.db.connection.execute("BEGIN IMMEDIATE")
        return self.db.connection

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            self.db.connection.execute("ROLLBACK" if exc_type else "COMMIT")
        finally:
            self.db.lock.release()
