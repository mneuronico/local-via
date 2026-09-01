import asyncio
import json
import mimetypes
import shutil
import uuid
from functools import partial
from pathlib import Path
from .database import Database


class JobService:
    def __init__(self, db: Database, backend, data_dir: Path):
        self.db, self.backend, self.data_dir = db, backend, data_dir
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.active_job_id: str | None = None
        self.task: asyncio.Task | None = None

    async def start(self) -> None:
        self.queue = asyncio.Queue()
        for job in self.db.all("SELECT id FROM jobs WHERE status IN ('queued','running') ORDER BY created_at"):
            self.db.update_job(job["id"], status="queued", progress=0, phase="recovered")
            await self.queue.put(job["id"])
        self.task = asyncio.create_task(self._runner())

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()
            try: await self.task
            except asyncio.CancelledError: pass
            self.task = None

    async def submit(self, payload: dict) -> str:
        job_id = uuid.uuid4().hex
        self.db.create_job(job_id, payload)
        await self.queue.put(job_id)
        return job_id

    async def cancel(self, job_id: str) -> None:
        row = self.db.one("SELECT status FROM jobs WHERE id=?", (job_id,))
        if not row: raise KeyError(job_id)
        if row["status"] == "running" and self.active_job_id == job_id: self.backend.cancel()
        self.db.update_job(job_id, status="cancelled", phase="cancelled")

    async def _runner(self) -> None:
        while True:
            job_id = await self.queue.get()
            row = self.db.one("SELECT * FROM jobs WHERE id=?", (job_id,))
            if not row or row["status"] == "cancelled": self.queue.task_done(); continue
            self.active_job_id = job_id
            self.db.update_job(job_id, status="running", progress=1, phase="loading")
            try:
                inputs = self._resolve_inputs(json.loads(row["inputs_json"]))
                payload = {**row, "inputs": json.loads(row["inputs_json"]), "parameters": json.loads(row["parameters_json"])}
                loop = asyncio.get_running_loop()
                def progress(value: int, phase: str):
                    changes = {"phase": phase}
                    if value >= 0: changes["progress"] = max(0, min(100, value))
                    loop.call_soon_threadsafe(partial(self.db.update_job, job_id, **changes))
                outputs = await self.backend.execute(payload, inputs, progress)
                if self.db.one("SELECT status FROM jobs WHERE id=?", (job_id,))["status"] != "cancelled":
                    self._save_artifacts(job_id, outputs)
                    self.db.update_job(job_id, status="succeeded", progress=100, phase="complete")
            except asyncio.CancelledError:
                self.db.update_job(job_id, status="cancelled", phase="cancelled")
            except Exception as error:
                self.db.update_job(job_id, status="failed", phase="error", error=str(error)[:2000])
            finally:
                self.active_job_id = None; self.queue.task_done()

    def _resolve_inputs(self, inputs: dict[str, str | list[str]]) -> dict[str, Path | list[Path]]:
        resolved: dict[str, Path | list[Path]] = {}
        for key, value in inputs.items():
            upload_ids = value if isinstance(value, list) else [value]
            paths: list[Path] = []
            for upload_id in upload_ids:
                row = self.db.one("SELECT path, complete FROM uploads WHERE id=?", (upload_id,))
                if not row or not row["complete"]: raise ValueError(f"Upload incompleto: {key}")
                paths.append(Path(row["path"]))
            resolved[key] = paths if isinstance(value, list) else paths[0]
        return resolved

    def _save_artifacts(self, job_id: str, outputs: list[Path]) -> None:
        target = self.data_dir / "jobs" / job_id / "output"; target.mkdir(parents=True, exist_ok=True)
        for source in outputs:
            if not source.exists(): continue
            destination = target / source.name
            if source.resolve() != destination.resolve(): shutil.copy2(source, destination)
            artifact_id = uuid.uuid4().hex
            media_type = mimetypes.guess_type(destination.name)[0] or "application/octet-stream"
            self.db.execute("INSERT INTO artifacts VALUES (?,?,?,?,?,?,?)", (artifact_id, job_id, destination.name, media_type, destination.stat().st_size, str(destination.resolve()), __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()))
