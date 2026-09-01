import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self._migrate()

    def _migrate(self) -> None:
        with self.lock, self.connection:
            self.connection.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS uploads (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, media_type TEXT NOT NULL,
                    expected_size INTEGER NOT NULL, path TEXT, complete INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL, model TEXT NOT NULL,
                    task TEXT NOT NULL, prompt TEXT NOT NULL, inputs_json TEXT NOT NULL,
                    parameters_json TEXT NOT NULL, status TEXT NOT NULL, progress INTEGER NOT NULL,
                    phase TEXT, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY, job_id TEXT NOT NULL, name TEXT NOT NULL,
                    media_type TEXT NOT NULL, size INTEGER NOT NULL, path TEXT NOT NULL,
                    created_at TEXT NOT NULL, FOREIGN KEY(job_id) REFERENCES jobs(id)
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_artifacts_job ON artifacts(job_id);
            """)

    def execute(self, sql: str, values: tuple[Any, ...] = ()) -> None:
        with self.lock, self.connection: self.connection.execute(sql, values)

    def one(self, sql: str, values: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self.lock:
            row = self.connection.execute(sql, values).fetchone()
            return dict(row) if row else None

    def all(self, sql: str, values: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.lock: return [dict(row) for row in self.connection.execute(sql, values).fetchall()]

    def create_job(self, job_id: str, payload: dict[str, Any]) -> None:
        stamp = now_iso()
        self.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            job_id, payload["project_id"], payload["model"], payload["task"], payload["prompt"],
            json.dumps(payload["inputs"]), json.dumps(payload["parameters"]), "queued", 0,
            "queued", None, stamp, stamp,
        ))

    def update_job(self, job_id: str, **changes: Any) -> None:
        allowed = {"status", "progress", "phase", "error"}
        fields = [(key, value) for key, value in changes.items() if key in allowed]
        if not fields: return
        fields.append(("updated_at", now_iso()))
        self.execute(f"UPDATE jobs SET {', '.join(f'{key}=?' for key, _ in fields)} WHERE id=?", tuple(value for _, value in fields) + (job_id,))

