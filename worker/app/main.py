import hashlib
import hmac
import json
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .backends import MockBackend, WanGPBackend
from .catalog import TASKS, public_catalog
from .config import settings
from .database import Database
from .schemas import JobCreate, UploadComplete, UploadCreate
from .service import JobService


settings.data_dir.mkdir(parents=True, exist_ok=True)
db = Database(settings.data_dir / "worker.db")
wangp_cli_args = settings.wangp_cli_args.split()
if settings.wangp_preload_mb > 0 and "--preload" not in wangp_cli_args:
    wangp_cli_args.extend(["--preload", str(settings.wangp_preload_mb)])
backend = WanGPBackend(settings.wangp_root, settings.data_dir / "wangp-outputs", wangp_cli_args, settings.model_idle_timeout_seconds, settings.wangp_preload_mb) if settings.backend == "wangp" else MockBackend(settings.data_dir / "mock-outputs")
service = JobService(db, backend, settings.data_dir)
security = HTTPBearer(auto_error=False)


def authorize(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> None:
    client_host = request.client.host if request.client else ""
    origin = request.headers.get("origin", "")
    origin_host = urlparse(origin).hostname if origin else None
    if client_host in {"127.0.0.1", "::1"} and origin_host in {"localhost", "127.0.0.1", "::1"}:
        return
    if credentials is None or not hmac.compare_digest(credentials.credentials, settings.token):
        raise HTTPException(401, "Token inválido")


def gpu_info():
    try:
        import pynvml
        pynvml.nvmlInit(); handle = pynvml.nvmlDeviceGetHandleByIndex(0); memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
        return {"name": pynvml.nvmlDeviceGetName(handle), "vram_total_mb": memory.total // 1024 // 1024, "vram_free_mb": memory.free // 1024 // 1024}
    except Exception: return None


def sign_file(artifact_id: str, expires: int) -> str:
    return hmac.new(settings.signing_secret.encode(), f"{artifact_id}:{expires}".encode(), hashlib.sha256).hexdigest()


def artifact_url_expiry(now: float | None = None) -> int:
    """Keep artifact URLs stable during polling while retaining finite-lived links."""
    current = int(time.time() if now is None else now)
    day = 86400
    return ((current // day) + 2) * day


def serialize_job(row: dict, request: Request) -> dict:
    row = dict(row)
    artifacts = db.all("SELECT * FROM artifacts WHERE job_id=? ORDER BY created_at", (row["id"],))
    base = settings.public_base_url.rstrip("/") or str(request.base_url).rstrip("/")
    for artifact in artifacts:
        expires = artifact_url_expiry()
        artifact["url"] = f"{base}/v1/files/{artifact['id']}?expires={expires}&signature={sign_file(artifact['id'], expires)}"
        artifact.pop("path", None); artifact.pop("job_id", None); artifact.pop("created_at", None)
    parameters = json.loads(row.pop("parameters_json"))
    inputs = json.loads(row.pop("inputs_json"))
    return {**row, "parameters": parameters, "artifacts": artifacts, "inputs": inputs}


@asynccontextmanager
async def lifespan(_: FastAPI):
    await service.start(); yield; await service.stop()


app = FastAPI(title="Local Via Worker", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=False, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health(): return {"ok": True}


@app.get("/v1/status", dependencies=[Depends(authorize)])
def status():
    model_cache = backend.cache_status() if isinstance(backend, WanGPBackend) else None
    return {"worker_id": settings.worker_id, "status": "busy" if service.active_job_id else "idle", "backend": backend.name, "gpu": gpu_info(), "queue_depth": service.queue.qsize(), "active_job_id": service.active_job_id, "wangp_ready": backend.ready, "model_cache": model_cache}


@app.get("/v1/models", dependencies=[Depends(authorize)])
def models(): return {"models": public_catalog(backend.availability())}


@app.post("/v1/uploads", dependencies=[Depends(authorize)])
def create_upload(payload: UploadCreate):
    upload_id = uuid.uuid4().hex; folder = settings.data_dir / "uploads" / upload_id / "chunks"; folder.mkdir(parents=True)
    db.execute("INSERT INTO uploads VALUES (?,?,?,?,?,?,?)", (upload_id, payload.name, payload.media_type, payload.size, None, 0, __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()))
    return {"id": upload_id}


@app.put("/v1/uploads/{upload_id}/chunks/{index}", dependencies=[Depends(authorize)])
async def upload_chunk(upload_id: str, index: int, chunk: UploadFile = File(...)):
    if index < 0 or not db.one("SELECT id FROM uploads WHERE id=?", (upload_id,)): raise HTTPException(404, "Upload inexistente")
    path = settings.data_dir / "uploads" / upload_id / "chunks" / f"{index:08d}.part"
    with path.open("wb") as target:
        while data := await chunk.read(1024 * 1024): target.write(data)
    return {"received": path.stat().st_size}


@app.post("/v1/uploads/{upload_id}/complete", dependencies=[Depends(authorize)])
def complete_upload(upload_id: str, payload: UploadComplete):
    row = db.one("SELECT * FROM uploads WHERE id=?", (upload_id,))
    if not row: raise HTTPException(404, "Upload inexistente")
    folder = settings.data_dir / "uploads" / upload_id; chunks = [folder / "chunks" / f"{index:08d}.part" for index in range(payload.chunks)]
    if not all(path.exists() for path in chunks): raise HTTPException(409, "Faltan fragmentos")
    destination = folder / Path(row["name"]).name
    with destination.open("wb") as target:
        for path in chunks:
            with path.open("rb") as source: shutil.copyfileobj(source, target)
    if destination.stat().st_size != row["expected_size"]: raise HTTPException(409, "El tamaño reconstruido no coincide")
    shutil.rmtree(folder / "chunks")
    db.execute("UPDATE uploads SET path=?, complete=1 WHERE id=?", (str(destination.resolve()), upload_id))
    return {"id": upload_id}


@app.post("/v1/jobs", dependencies=[Depends(authorize)])
async def create_job(payload: JobCreate, request: Request):
    if payload.model not in TASKS: raise HTTPException(422, "Modelo no soportado")
    if payload.task not in TASKS[payload.model]: raise HTTPException(422, "La tarea no corresponde al modelo")
    job_id = await service.submit(payload.model_dump())
    return serialize_job(db.one("SELECT * FROM jobs WHERE id=?", (job_id,)), request)


@app.get("/v1/jobs", dependencies=[Depends(authorize)])
def list_jobs(request: Request, limit: int = 50):
    return {"jobs": [serialize_job(row, request) for row in db.all("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (min(limit, 200),))]}


@app.get("/v1/jobs/{job_id}", dependencies=[Depends(authorize)])
def get_job(job_id: str, request: Request):
    row = db.one("SELECT * FROM jobs WHERE id=?", (job_id,))
    if not row: raise HTTPException(404, "Trabajo inexistente")
    return serialize_job(row, request)


@app.post("/v1/jobs/{job_id}/cancel", dependencies=[Depends(authorize)])
async def cancel_job(job_id: str, request: Request):
    try: await service.cancel(job_id)
    except KeyError: raise HTTPException(404, "Trabajo inexistente")
    return serialize_job(db.one("SELECT * FROM jobs WHERE id=?", (job_id,)), request)


@app.get("/v1/files/{artifact_id}")
def get_file(artifact_id: str, expires: int, signature: str):
    if expires < int(time.time()) or not hmac.compare_digest(signature, sign_file(artifact_id, expires)): raise HTTPException(403, "Enlace vencido o inválido")
    artifact = db.one("SELECT * FROM artifacts WHERE id=?", (artifact_id,))
    if not artifact or not Path(artifact["path"]).exists(): raise HTTPException(404, "Archivo inexistente")
    return FileResponse(artifact["path"], media_type=artifact["media_type"], filename=artifact["name"])
