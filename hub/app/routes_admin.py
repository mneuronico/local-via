import secrets
import time
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from .catalog import DEFAULT_POLICY, MODEL_NAMES
from .context import Hub, admin_user, client_ip, hub
from .routes_student import USERNAME, remove_job_files
from .security import hash_password, new_class_code, new_token, token_hash
from .serialize import iso, job_out, user_out, worker_out

router = APIRouter(prefix="/api/admin")


def readable_password() -> str:
    alphabet = "abcdefghijkmnpqrstuvwxyz23456789"
    return "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(3))


class UserCreate(BaseModel):
    username: str = Field(max_length=40)
    display_name: str = Field(default="", max_length=80)
    password: str | None = Field(default=None, min_length=8, max_length=200)
    role: str = Field(default="student", pattern="^(student|admin)$")
    class_id: str | None = None


class BulkUsers(BaseModel):
    usernames: list[str] = Field(max_length=200)
    class_id: str | None = None


class UserPatch(BaseModel):
    disabled: bool | None = None
    role: str | None = Field(default=None, pattern="^(student|admin)$")
    reset_password: bool = False


class ClassCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    expires_in_days: int | None = Field(default=120, ge=1, le=730)
    max_uses: int | None = Field(default=None, ge=1, le=2000)


class ClassPatch(BaseModel):
    revoked: bool


class WorkerCreate(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9._-]{2,40}$")


class WorkerPatch(BaseModel):
    disabled: bool


class Policy(BaseModel):
    enabled_models: list[str]
    max_pixels: int = Field(ge=64 * 64, le=4096 * 4096)
    max_video_frames: int = Field(ge=1, le=2000)
    max_steps: int = Field(ge=1, le=200)
    max_audio_seconds: int = Field(ge=1, le=600)
    max_batch_size: int = Field(ge=1, le=16)


def audit(state: Hub, request: Request, admin: dict, action: str, detail: str | None = None) -> None:
    state.db.audit(action, admin["username"], detail, client_ip(request))


def create_user_row(state: Hub, username: str, display_name: str, password: str, role: str, class_id: str | None) -> dict:
    username = username.strip().lower()
    if not USERNAME.match(username): raise HTTPException(422, f"Usuario inválido: {username}")
    if class_id and not state.db.one("SELECT id FROM classes WHERE id=?", (class_id,)): raise HTTPException(404, "Clase inexistente")
    if state.db.one("SELECT id FROM users WHERE username=?", (username,)): raise HTTPException(409, f"El usuario {username} ya existe")
    user_id = uuid.uuid4().hex
    state.db.execute("INSERT INTO users (id, username, display_name, password_hash, role, class_id, created_at) VALUES (?,?,?,?,?,?,?)",
                     (user_id, username, display_name.strip() or username, hash_password(password), role, class_id, time.time()))
    return state.db.one("SELECT * FROM users WHERE id=?", (user_id,))


@router.get("/overview")
def overview(admin: dict = Depends(admin_user), state: Hub = Depends(hub)):
    online = {worker["id"] for worker in state.scheduler.online_workers()}
    snapshot = state.scheduler.queue_snapshot()
    active = state.db.all("SELECT j.*, u.username FROM jobs j JOIN users u ON u.id=j.user_id WHERE j.status IN ('queued','running') ORDER BY j.created_at")
    since = time.time() - 86400
    stats = state.db.one("SELECT COUNT(*) AS total, SUM(status='succeeded') AS succeeded, SUM(status='failed') AS failed FROM jobs WHERE created_at >= ?", (since,))
    return {
        "workers": [worker_out(row, row["id"] in online) for row in state.db.all("SELECT * FROM workers ORDER BY id")],
        "queue": [job_out(row, [], snapshot["positions"].get(row["id"]), row["username"]) for row in active],
        "room": {key: snapshot[key] for key in ("queued_total", "running_total", "workers_online", "workers_busy")},
        "last_24h": {key: stats[key] or 0 for key in ("total", "succeeded", "failed")},
        "users_total": state.db.one("SELECT COUNT(*) AS n FROM users")["n"],
    }


@router.get("/users")
def list_users(admin: dict = Depends(admin_user), state: Hub = Depends(hub)):
    return {"users": [user_out(row) for row in state.db.all("SELECT * FROM users ORDER BY role, username")]}


@router.post("/users")
def create_user(payload: UserCreate, request: Request, admin: dict = Depends(admin_user), state: Hub = Depends(hub)):
    password = payload.password or readable_password()
    user = create_user_row(state, payload.username, payload.display_name, password, payload.role, payload.class_id)
    audit(state, request, admin, "user_created", f"{user['username']} ({user['role']})")
    return {"user": user_out(user), "password": None if payload.password else password}


@router.post("/users/bulk")
def bulk_users(payload: BulkUsers, request: Request, admin: dict = Depends(admin_user), state: Hub = Depends(hub)):
    created = []
    for username in dict.fromkeys(name.strip().lower() for name in payload.usernames if name.strip()):
        password = readable_password()
        user = create_user_row(state, username, username, password, "student", payload.class_id)
        created.append({"username": user["username"], "password": password})
    audit(state, request, admin, "users_bulk_created", f"{len(created)} usuarios")
    return {"created": created}


@router.patch("/users/{user_id}")
def patch_user(user_id: str, payload: UserPatch, request: Request, admin: dict = Depends(admin_user), state: Hub = Depends(hub)):
    user = state.db.one("SELECT * FROM users WHERE id=?", (user_id,))
    if not user: raise HTTPException(404, "Usuario inexistente")
    if user_id == admin["id"] and (payload.disabled or payload.role == "student"): raise HTTPException(409, "No podés quitarte tu propio acceso de administración")
    result: dict = {}
    if payload.disabled is not None:
        state.db.execute("UPDATE users SET disabled=? WHERE id=?", (int(payload.disabled), user_id))
        if payload.disabled: state.db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    if payload.role: state.db.execute("UPDATE users SET role=? WHERE id=?", (payload.role, user_id))
    if payload.reset_password:
        result["password"] = readable_password()
        state.db.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(result["password"]), user_id))
        state.db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    audit(state, request, admin, "user_updated", f"{user['username']}: {payload.model_dump(exclude_defaults=True)}")
    return {"user": user_out(state.db.one("SELECT * FROM users WHERE id=?", (user_id,))), **result}


@router.delete("/users/{user_id}")
def delete_user(user_id: str, request: Request, admin: dict = Depends(admin_user), state: Hub = Depends(hub)):
    user = state.db.one("SELECT * FROM users WHERE id=?", (user_id,))
    if not user: raise HTTPException(404, "Usuario inexistente")
    if user_id == admin["id"]: raise HTTPException(409, "No podés borrar tu propia cuenta")
    for job in state.db.all("SELECT id, status FROM jobs WHERE user_id=?", (user_id,)):
        if job["status"] in ("queued", "running"): state.scheduler.cancel(job["id"])
        remove_job_files(state, job["id"])
    for upload in state.db.all("SELECT path FROM uploads WHERE user_id=?", (user_id,)):
        Path(upload["path"]).unlink(missing_ok=True)
    state.db.execute("DELETE FROM users WHERE id=?", (user_id,))
    audit(state, request, admin, "user_deleted", user["username"])
    return {"ok": True}


@router.get("/classes")
def list_classes(admin: dict = Depends(admin_user), state: Hub = Depends(hub)):
    rows = state.db.all("SELECT c.*, (SELECT COUNT(*) FROM users u WHERE u.class_id=c.id) AS students FROM classes c ORDER BY created_at DESC")
    return {"classes": [{**row, "expires_at": iso(row["expires_at"]), "created_at": iso(row["created_at"]), "revoked": bool(row["revoked"])} for row in rows]}


@router.post("/classes")
def create_class(payload: ClassCreate, request: Request, admin: dict = Depends(admin_user), state: Hub = Depends(hub)):
    class_id, code, now = uuid.uuid4().hex, new_class_code(), time.time()
    expires = now + payload.expires_in_days * 86400 if payload.expires_in_days else None
    state.db.execute("INSERT INTO classes (id, name, code, expires_at, max_uses, created_at) VALUES (?,?,?,?,?,?)",
                     (class_id, payload.name.strip(), code, expires, payload.max_uses, now))
    audit(state, request, admin, "class_created", payload.name)
    return {"id": class_id, "code": code}


@router.patch("/classes/{class_id}")
def patch_class(class_id: str, payload: ClassPatch, request: Request, admin: dict = Depends(admin_user), state: Hub = Depends(hub)):
    if not state.db.execute("UPDATE classes SET revoked=? WHERE id=?", (int(payload.revoked), class_id)): raise HTTPException(404, "Clase inexistente")
    audit(state, request, admin, "class_updated", f"{class_id} revoked={payload.revoked}")
    return {"ok": True}


@router.get("/workers")
def list_workers(admin: dict = Depends(admin_user), state: Hub = Depends(hub)):
    online = {worker["id"] for worker in state.scheduler.online_workers()}
    return {"workers": [worker_out(row, row["id"] in online) for row in state.db.all("SELECT * FROM workers ORDER BY id")]}


@router.post("/workers")
def create_worker(payload: WorkerCreate, request: Request, admin: dict = Depends(admin_user), state: Hub = Depends(hub)):
    if state.db.one("SELECT id FROM workers WHERE id=?", (payload.id,)): raise HTTPException(409, "Ya existe un worker con ese nombre")
    token = new_token()
    state.db.execute("INSERT INTO workers (id, token_hash, created_at) VALUES (?,?,?)", (payload.id, token_hash(token), time.time()))
    audit(state, request, admin, "worker_created", payload.id)
    return {"id": payload.id, "token": token}


@router.post("/workers/{worker_id}/rotate")
def rotate_worker(worker_id: str, request: Request, admin: dict = Depends(admin_user), state: Hub = Depends(hub)):
    token = new_token()
    if not state.db.execute("UPDATE workers SET token_hash=? WHERE id=?", (token_hash(token), worker_id)): raise HTTPException(404, "Worker inexistente")
    audit(state, request, admin, "worker_token_rotated", worker_id)
    return {"id": worker_id, "token": token}


@router.patch("/workers/{worker_id}")
def patch_worker(worker_id: str, payload: WorkerPatch, request: Request, admin: dict = Depends(admin_user), state: Hub = Depends(hub)):
    if not state.db.execute("UPDATE workers SET disabled=? WHERE id=?", (int(payload.disabled), worker_id)): raise HTTPException(404, "Worker inexistente")
    audit(state, request, admin, "worker_updated", f"{worker_id} disabled={payload.disabled}")
    return {"ok": True}


@router.delete("/workers/{worker_id}")
def delete_worker(worker_id: str, request: Request, admin: dict = Depends(admin_user), state: Hub = Depends(hub)):
    if not state.db.execute("DELETE FROM workers WHERE id=?", (worker_id,)): raise HTTPException(404, "Worker inexistente")
    audit(state, request, admin, "worker_deleted", worker_id)
    return {"ok": True}


@router.post("/jobs/{job_id}/cancel")
def cancel_any_job(job_id: str, request: Request, admin: dict = Depends(admin_user), state: Hub = Depends(hub)):
    state.scheduler.cancel(job_id)
    audit(state, request, admin, "job_cancelled", job_id)
    return {"ok": True}


@router.get("/policy")
def get_policy(admin: dict = Depends(admin_user), state: Hub = Depends(hub)):
    return {"policy": state.policy(), "defaults": DEFAULT_POLICY, "models": [{"id": key, "name": value} for key, value in MODEL_NAMES.items()]}


@router.put("/policy")
def put_policy(payload: Policy, request: Request, admin: dict = Depends(admin_user), state: Hub = Depends(hub)):
    unknown = [model for model in payload.enabled_models if model not in MODEL_NAMES]
    if unknown: raise HTTPException(422, f"Modelos desconocidos: {', '.join(unknown)}")
    state.save_policy(payload.model_dump())
    audit(state, request, admin, "policy_updated", None)
    return {"policy": state.policy()}


@router.get("/audit")
def get_audit(admin: dict = Depends(admin_user), state: Hub = Depends(hub)):
    rows = state.db.all("SELECT * FROM audit ORDER BY id DESC LIMIT 300")
    return {"events": [{**row, "at": iso(row["at"])} for row in rows]}
