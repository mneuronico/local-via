import asyncio
import json
import mimetypes
import re
import time
import uuid
from pathlib import Path
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from .context import Hub, current_worker, hub, peer_ip

router = APIRouter(prefix="/worker-api")
OUTPUT_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif",
                ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime", ".mkv": "video/x-matroska",
                ".wav": "audio/wav", ".mp3": "audio/mpeg", ".flac": "audio/flac", ".ogg": "audio/ogg", ".m4a": "audio/mp4"}


class WorkerState(BaseModel):
    backend: str | None = None
    version: str | None = None
    loaded_model: str | None = None
    gpu: dict[str, Any] | None = None
    installed_models: list[str] | None = None


class Claim(BaseModel):
    state: WorkerState = Field(default_factory=WorkerState)


class ProgressReport(BaseModel):
    progress: int | None = None
    phase: str | None = Field(default=None, max_length=60)


class Finish(BaseModel):
    status: str = Field(pattern="^(succeeded|failed|cancelled)$")
    error: str | None = Field(default=None, max_length=4000)


def assigned_job(state: Hub, worker: dict, job_id: str) -> dict:
    job = state.db.one("SELECT * FROM jobs WHERE id=?", (job_id,))
    if not job or job["worker_id"] != worker["id"] or job["status"] != "running": raise HTTPException(409, "El trabajo ya no está asignado a este worker")
    return job


def job_for_worker(state: Hub, job: dict) -> dict:
    inputs = json.loads(job["inputs_json"])
    described: dict[str, list[dict]] = {}
    for key, value in inputs.items():
        ids = value if isinstance(value, list) else [value]
        rows = [state.db.one("SELECT id, name, media_type, expected_size FROM uploads WHERE id=?", (upload_id,)) for upload_id in ids]
        described[key] = [{"id": row["id"], "name": row["name"], "media_type": row["media_type"], "size": row["expected_size"]} for row in rows if row]
    return {"id": job["id"], "model": job["model"], "task": job["task"], "prompt": job["prompt"], "parameters": json.loads(job["parameters_json"]),
            "inputs": described, "input_is_list": {key: isinstance(value, list) for key, value in inputs.items()},
            "lease_seconds": state.settings.lease_seconds}


@router.post("/claim")
async def claim(payload: Claim, request: Request, worker: dict = Depends(current_worker), state: Hub = Depends(hub)):
    """Long poll: returns a job as soon as one is runnable, or 204 after claim_wait_seconds."""
    state.scheduler.touch_worker(worker["id"], peer_ip(request), payload.state.model_dump())
    deadline = time.monotonic() + state.settings.claim_wait_seconds
    while True:
        job = state.scheduler.claim(worker["id"])
        if job: return job_for_worker(state, job)
        remaining = deadline - time.monotonic()
        if remaining <= 0 or await request.is_disconnected(): return Response(status_code=204)
        try: await asyncio.wait_for(state.wake.wait(), timeout=min(remaining, 2.0))
        except asyncio.TimeoutError: pass
        state.scheduler.touch_worker(worker["id"], peer_ip(request))


@router.get("/jobs/{job_id}/inputs/{upload_id}")
def job_input(job_id: str, upload_id: str, worker: dict = Depends(current_worker), state: Hub = Depends(hub)):
    job = assigned_job(state, worker, job_id)
    inputs = json.loads(job["inputs_json"])
    referenced = {item for value in inputs.values() for item in (value if isinstance(value, list) else [value])}
    if upload_id not in referenced: raise HTTPException(404, "El archivo no pertenece a este trabajo")
    upload = state.db.one("SELECT * FROM uploads WHERE id=? AND complete=1", (upload_id,))
    if not upload: raise HTTPException(404, "Archivo inexistente")
    return FileResponse(upload["path"], media_type="application/octet-stream")


@router.post("/jobs/{job_id}/progress")
def progress(job_id: str, payload: ProgressReport, worker: dict = Depends(current_worker), state: Hub = Depends(hub)):
    return {"cancel": state.scheduler.progress(worker["id"], job_id, payload.progress, payload.phase)}


@router.put("/jobs/{job_id}/artifacts")
async def upload_artifact(job_id: str, name: str, request: Request, worker: dict = Depends(current_worker), state: Hub = Depends(hub)):
    job = assigned_job(state, worker, job_id)
    clean = re.sub(r"[^A-Za-z0-9._-]", "_", Path(name).name)[:120] or "resultado"
    suffix = Path(clean).suffix.lower()
    if suffix not in OUTPUT_TYPES: raise HTTPException(422, f"Tipo de resultado no admitido: {suffix or 'sin extensión'}")
    folder = state.outputs_dir / job_id; folder.mkdir(parents=True, exist_ok=True)
    artifact_id = uuid.uuid4().hex
    path = folder / f"{artifact_id}{suffix}"
    limit, written = state.settings.max_output_mb * 1024 * 1024, 0
    try:
        with path.open("wb") as target:
            async for data in request.stream():
                written += len(data)
                if written > limit: raise HTTPException(413, "Resultado demasiado grande")
                target.write(data)
    except BaseException:
        path.unlink(missing_ok=True); raise
    media_type = OUTPUT_TYPES.get(suffix) or mimetypes.guess_type(clean)[0] or "application/octet-stream"
    state.db.execute("INSERT INTO artifacts (id, job_id, user_id, name, media_type, size, path, created_at) VALUES (?,?,?,?,?,?,?,?)",
                     (artifact_id, job_id, job["user_id"], clean, media_type, written, str(path), time.time()))
    state.scheduler.progress(worker["id"], job_id, None, "uploading_output")
    return {"id": artifact_id, "size": written}


@router.post("/jobs/{job_id}/complete")
def complete(job_id: str, payload: Finish, worker: dict = Depends(current_worker), state: Hub = Depends(hub)):
    if payload.status == "succeeded" and not state.db.one("SELECT id FROM artifacts WHERE job_id=?", (job_id,)):
        state.scheduler.finish(worker["id"], job_id, "failed", "El worker no devolvió ningún archivo")
    else:
        state.scheduler.finish(worker["id"], job_id, payload.status, payload.error)
    return {"ok": True}
