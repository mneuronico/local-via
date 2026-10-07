"""Global job queue: dispatch to pulling workers, leases, cancellation and wait estimates."""
import json
import statistics
import time
import uuid
from .catalog import DEFAULT_DURATION, output_kind
from .config import HubSettings
from .db import Database


class Scheduler:
    def __init__(self, db: Database, settings: HubSettings):
        self.db, self.settings = db, settings

    # ---- workers -------------------------------------------------------------------------
    def online_workers(self, now: float | None = None) -> list[dict]:
        cutoff = (now or time.time()) - self.settings.worker_offline_seconds
        return self.db.all("SELECT * FROM workers WHERE disabled=0 AND last_seen_at IS NOT NULL AND last_seen_at >= ? ORDER BY id", (cutoff,))

    def touch_worker(self, worker_id: str, ip: str, state: dict | None = None) -> None:
        """Marks the worker alive; when the agent sent its state, stores it too."""
        if state is None:
            self.db.execute("UPDATE workers SET last_seen_at=? WHERE id=?", (time.time(), worker_id))
            return
        installed = state.get("installed_models")
        self.db.execute(
            "UPDATE workers SET last_seen_at=?, ip=?, backend=?, version=?, loaded_model=?, gpu_json=?, installed_json=COALESCE(?, installed_json) WHERE id=?",
            (time.time(), ip, str(state.get("backend") or "")[:40], str(state.get("version") or "")[:40], state.get("loaded_model"),
             json.dumps(state.get("gpu")) if state.get("gpu") else None, json.dumps(installed) if isinstance(installed, list) else None, worker_id),
        )

    def available_models(self) -> set[str]:
        """Models installed on at least one online worker. A mock worker reports every model."""
        models: set[str] = set()
        for worker in self.online_workers():
            models.update(json.loads(worker["installed_json"] or "[]"))
        return models

    # ---- jobs ------------------------------------------------------------------------------
    def submit(self, user_id: str, payload: dict) -> str:
        job_id = uuid.uuid4().hex
        now = time.time()
        self.db.execute(
            "INSERT INTO jobs (id, user_id, model, task, prompt, inputs_json, parameters_json, status, progress, phase, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (job_id, user_id, payload["model"], payload["task"], payload["prompt"], json.dumps(payload["inputs"]), json.dumps(payload["parameters"]), "queued", 0, "queued", now, now),
        )
        return job_id

    def claim(self, worker_id: str) -> dict | None:
        """Atomically give the calling worker the best queued job it can run, or None."""
        worker = self.db.one("SELECT * FROM workers WHERE id=?", (worker_id,))
        if not worker or worker["disabled"]: return None
        installed = set(json.loads(worker["installed_json"] or "[]"))
        loaded = worker["loaded_model"]
        now = time.time()
        with self.db.transaction() as connection:
            # A worker only claims when idle, so anything still assigned to it was lost (crash/restart).
            for lost in connection.execute("SELECT id, attempts, cancel_requested FROM jobs WHERE status='running' AND worker_id=?", (worker_id,)).fetchall():
                self._release(connection, dict(lost), now)
            queued = [dict(row) for row in connection.execute("SELECT id, model, created_at FROM jobs WHERE status='queued' ORDER BY created_at, id").fetchall()]
            runnable = [job for job in queued if job["model"] in installed]
            if not runnable: return None
            oldest = runnable[0]
            chosen = oldest
            if loaded and oldest["model"] != loaded:
                warm = next((job for job in runnable if job["model"] == loaded), None)
                if warm and warm["created_at"] - oldest["created_at"] <= self.settings.affinity_window_seconds:
                    chosen = warm
            lease = now + self.settings.lease_seconds
            connection.execute(
                "UPDATE jobs SET status='running', worker_id=?, attempts=attempts+1, claimed_at=?, lease_expires_at=?, phase='dispatched', progress=0, updated_at=? WHERE id=? AND status='queued'",
                (worker_id, now, lease, now, chosen["id"]),
            )
            connection.execute("UPDATE workers SET current_job_id=? WHERE id=?", (chosen["id"], worker_id))
        return self.db.one("SELECT * FROM jobs WHERE id=?", (chosen["id"],))

    def progress(self, worker_id: str, job_id: str, value: int | None, phase: str | None) -> bool:
        """Records progress, renews the lease and returns True when the worker must stop."""
        job = self.db.one("SELECT status, cancel_requested, worker_id FROM jobs WHERE id=?", (job_id,))
        if not job or job["worker_id"] != worker_id or job["status"] != "running": return True
        now = time.time()
        changes = ["lease_expires_at=?", "updated_at=?"]; values: list = [now + self.settings.lease_seconds, now]
        if value is not None and value >= 0: changes.append("progress=?"); values.append(max(0, min(99, int(value))))
        if phase: changes.append("phase=?"); values.append(phase[:60])
        self.db.execute(f"UPDATE jobs SET {', '.join(changes)} WHERE id=? AND status='running'", (*values, job_id))
        self.db.execute("UPDATE workers SET last_seen_at=? WHERE id=?", (now, worker_id))
        return bool(job["cancel_requested"])

    def finish(self, worker_id: str, job_id: str, status: str, error: str | None = None) -> None:
        now = time.time()
        job = self.db.one("SELECT status, worker_id, cancel_requested FROM jobs WHERE id=?", (job_id,))
        if not job or job["worker_id"] != worker_id: return
        if job["status"] == "running":
            final = "cancelled" if job["cancel_requested"] or status == "cancelled" else status
            phase = {"succeeded": "complete", "failed": "error", "cancelled": "cancelled"}[final]
            self.db.execute(
                "UPDATE jobs SET status=?, phase=?, progress=?, error=?, finished_at=?, lease_expires_at=NULL, updated_at=? WHERE id=?",
                (final, phase, 100 if final == "succeeded" else 0, (error or "")[:2000] or None, now, now, job_id),
            )
        self.db.execute("UPDATE workers SET current_job_id=NULL, last_seen_at=? WHERE id=? AND current_job_id=?", (now, worker_id, job_id))

    def cancel(self, job_id: str) -> None:
        now = time.time()
        with self.db.transaction() as connection:
            row = connection.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row: return
            if row["status"] == "queued":
                connection.execute("UPDATE jobs SET status='cancelled', phase='cancelled', finished_at=?, updated_at=? WHERE id=?", (now, now, job_id))
            elif row["status"] == "running":
                # The worker learns about it on its next progress report (every few seconds).
                connection.execute("UPDATE jobs SET cancel_requested=1, phase='cancelling', updated_at=? WHERE id=?", (now, job_id))

    def reap(self) -> list[str]:
        """Requeues jobs whose worker stopped renewing its lease; fails them after max attempts."""
        now = time.time()
        with self.db.transaction() as connection:
            expired = [dict(row) for row in connection.execute("SELECT id, worker_id, attempts, cancel_requested FROM jobs WHERE status='running' AND lease_expires_at < ?", (now,)).fetchall()]
            for job in expired:
                self._release(connection, job, now)
                connection.execute("UPDATE workers SET current_job_id=NULL WHERE id=? AND current_job_id=?", (job["worker_id"], job["id"]))
        return [job["id"] for job in expired]

    @staticmethod
    def _release_status(job: dict, max_attempts: int) -> str:
        if job["cancel_requested"]: return "cancelled"
        return "queued" if job["attempts"] < max_attempts else "failed"

    def _release(self, connection, job: dict, now: float) -> None:
        status = self._release_status(job, self.settings.max_job_attempts)
        if status == "queued":
            # created_at is preserved, so the job goes back to the front of the queue.
            connection.execute("UPDATE jobs SET status='queued', phase='requeued', progress=0, worker_id=NULL, lease_expires_at=NULL, updated_at=? WHERE id=?", (now, job["id"]))
        elif status == "cancelled":
            connection.execute("UPDATE jobs SET status='cancelled', phase='cancelled', lease_expires_at=NULL, finished_at=?, updated_at=? WHERE id=?", (now, now, job["id"]))
        else:
            connection.execute("UPDATE jobs SET status='failed', phase='error', error=?, lease_expires_at=NULL, finished_at=?, updated_at=? WHERE id=?",
                               ("La computadora que procesaba el trabajo dejó de responder.", now, now, job["id"]))

    # ---- estimates -------------------------------------------------------------------------
    def expected_duration(self, model: str, task: str, cache: dict | None = None) -> float:
        key = (model, task)
        if cache is not None and key in cache: return cache[key]
        rows = self.db.all(
            "SELECT finished_at - claimed_at AS d FROM jobs WHERE model=? AND task=? AND status='succeeded' AND claimed_at IS NOT NULL ORDER BY finished_at DESC LIMIT 20",
            (model, task),
        )
        durations = [row["d"] for row in rows if row["d"] and row["d"] > 0]
        value = statistics.median(durations) if durations else DEFAULT_DURATION[output_kind(task)]
        if cache is not None: cache[key] = value
        return value

    def queue_snapshot(self) -> dict:
        """Position and estimated start time for every queued job (simulated FIFO over online workers)."""
        now = time.time()
        workers = self.online_workers(now)
        running = self.db.all("SELECT id, model, task, claimed_at, worker_id FROM jobs WHERE status='running'")
        queued = self.db.all("SELECT id, model, task FROM jobs WHERE status='queued' ORDER BY created_at, id")
        cache: dict = {}
        free_at = []
        busy = {job["worker_id"]: job for job in running}
        for worker in workers:
            job = busy.get(worker["id"])
            if job:
                remaining = self.expected_duration(job["model"], job["task"], cache) - (now - (job["claimed_at"] or now))
                free_at.append(max(30.0, remaining))
            else:
                free_at.append(0.0)
        positions: dict[str, dict] = {}
        for index, job in enumerate(queued):
            if free_at:
                slot = min(range(len(free_at)), key=free_at.__getitem__)
                start = free_at[slot]
                free_at[slot] = start + self.expected_duration(job["model"], job["task"], cache)
                wait = round(start)
            else:
                wait = None
            positions[job["id"]] = {"position": index + 1, "estimated_wait_seconds": wait}
        return {
            "positions": positions,
            "queued_total": len(queued),
            "running_total": len(running),
            "workers_online": len(workers),
            "workers_busy": sum(1 for worker in workers if worker["id"] in busy),
        }
