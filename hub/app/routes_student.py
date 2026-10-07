import hashlib
import json
import math
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from .catalog import ALLOWED_PARAMETERS, INPUT_KINDS, MAX_FILES_PER_INPUT, MODEL_NAMES, TASKS
from .context import Hub, client_ip, current_user, hub
from .security import DUMMY_PASSWORD_HASH, hash_password, new_token, sniff_media, token_hash, verify_password
from .serialize import job_out, user_out

router = APIRouter(prefix="/api")
CHUNK_BYTES = 8 * 1024 * 1024
USERNAME = re.compile(r"^[a-zA-Z0-9._-]{3,40}$")


class Login(BaseModel):
    username: str = Field(max_length=40)
    password: str = Field(max_length=200)


class Register(BaseModel):
    class_code: str = Field(max_length=20)
    username: str = Field(max_length=40)
    display_name: str = Field(default="", max_length=80)
    password: str = Field(min_length=8, max_length=200)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class UploadCreate(BaseModel):
    name: str = Field(max_length=255)
    size: int = Field(gt=0)
    media_type: str = Field(default="application/octet-stream", max_length=100)
    input_key: str


class JobCreate(BaseModel):
    model: str = Field(max_length=80)
    task: str = Field(max_length=40)
    prompt: str = ""
    inputs: dict[str, str | list[str]] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)


def start_session(state: Hub, response: Response, user: dict, request: Request) -> None:
    token = new_token()
    now = time.time()
    state.db.execute("INSERT INTO sessions (token_hash, user_id, created_at, expires_at, ip) VALUES (?,?,?,?,?)",
                     (token_hash(token), user["id"], now, now + state.settings.session_hours * 3600, client_ip(request)))
    state.db.execute("UPDATE users SET last_login_at=? WHERE id=?", (now, user["id"]))
    response.set_cookie(state.cookie_name, token, max_age=state.settings.session_hours * 3600, httponly=True,
                        secure=state.settings.secure_cookies, samesite="strict", path="/")


def me_out(state: Hub, user: dict) -> dict:
    return {"user": user_out(user), "limits": {"max_active_jobs": state.settings.max_active_jobs_per_user, "max_upload_mb": state.settings.max_upload_mb,
            "quota_mb": state.settings.user_quota_mb, "retention_days": state.settings.retention_days}}


@router.post("/auth/login")
def login(payload: Login, request: Request, response: Response, state: Hub = Depends(hub)):
    ip, name = client_ip(request), payload.username.strip().lower()
    keys = (f"ip:{ip}", f"user:{name}")
    if state.login_limiter.blocked(keys[1]) or state.login_limiter.blocked(keys[0], limit=state.settings.login_max_failures * 4):
        raise HTTPException(429, f"Demasiados intentos. Esperá {state.settings.login_window_minutes} minutos.")
    user = state.db.one("SELECT * FROM users WHERE username=?", (name,))
    valid = verify_password(payload.password, user["password_hash"] if user else DUMMY_PASSWORD_HASH)
    if not user or not valid or user["disabled"]:
        state.login_limiter.fail(*keys)
        state.db.audit("login_failed", name, None, ip)
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    state.login_limiter.reset(keys[1])
    start_session(state, response, user, request)
    state.db.audit("login", user["username"], None, ip)
    return me_out(state, user)


@router.post("/auth/register")
def register(payload: Register, request: Request, response: Response, state: Hub = Depends(hub)):
    ip = client_ip(request)
    if state.register_limiter.blocked(f"ip:{ip}"): raise HTTPException(429, "Demasiados intentos. Probá más tarde.")
    code = payload.class_code.strip().upper()
    username = payload.username.strip().lower()
    if not USERNAME.match(username): raise HTTPException(422, "El usuario admite de 3 a 40 letras, números, punto, guion o guion bajo")
    now = time.time()
    with state.db.transaction() as connection:
        group = connection.execute("SELECT * FROM classes WHERE code=?", (code,)).fetchone()
        if not group or group["revoked"] or (group["expires_at"] and group["expires_at"] < now) or (group["max_uses"] and group["uses"] >= group["max_uses"]):
            state.register_limiter.fail(f"ip:{ip}")
            raise HTTPException(403, "El código de clase no es válido o ya venció")
        if connection.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            raise HTTPException(409, "Ese usuario ya existe")
        user_id = uuid.uuid4().hex
        connection.execute("INSERT INTO users (id, username, display_name, password_hash, role, class_id, created_at) VALUES (?,?,?,?,?,?,?)",
                           (user_id, username, payload.display_name.strip() or username, hash_password(payload.password), "student", group["id"], now))
        connection.execute("UPDATE classes SET uses=uses+1 WHERE id=?", (group["id"],))
    user = state.db.one("SELECT * FROM users WHERE id=?", (user_id,))
    state.db.audit("register", username, f"class={group['name']}", ip)
    start_session(state, response, user, request)
    return me_out(state, user)


@router.post("/auth/logout")
def logout(request: Request, response: Response, state: Hub = Depends(hub)):
    token = request.cookies.get(state.cookie_name)
    if token: state.db.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(token),))
    response.delete_cookie(state.cookie_name, path="/", secure=state.settings.secure_cookies, httponly=True, samesite="strict")
    return {"ok": True}


@router.get("/me")
def me(user: dict = Depends(current_user), state: Hub = Depends(hub)):
    return me_out(state, user)


@router.get("/session")
def session(request: Request, state: Hub = Depends(hub)):
    """Like /me, but answers 200 without a session so the login screen loads without an error."""
    try: return me_out(state, current_user(request, state))
    except HTTPException: return {"user": None}


@router.post("/me/password")
def change_password(payload: PasswordChange, request: Request, user: dict = Depends(current_user), state: Hub = Depends(hub)):
    if not verify_password(payload.current_password, user["password_hash"]): raise HTTPException(403, "La contraseña actual no coincide")
    state.db.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(payload.new_password), user["id"]))
    current = request.cookies.get(state.cookie_name, "")
    state.db.execute("DELETE FROM sessions WHERE user_id=? AND token_hash<>?", (user["id"], token_hash(current)))
    state.db.audit("password_changed", user["username"], None, client_ip(request))
    return {"ok": True}


@router.get("/catalog")
def catalog(user: dict = Depends(current_user), state: Hub = Depends(hub)):
    policy = state.policy()
    available = state.scheduler.available_models()
    return {"models": [{"id": model_id, "name": MODEL_NAMES[model_id], "enabled": model_id in policy["enabled_models"], "available": model_id in available}
                       for model_id in MODEL_NAMES], "policy": policy}


@router.get("/state")
def job_state(request: Request, user: dict = Depends(current_user), state: Hub = Depends(hub)):
    """Everything the studio polls, in one small response. Unchanged state is answered with 304."""
    snapshot = state.scheduler.queue_snapshot()
    rows = state.db.all("SELECT * FROM jobs WHERE user_id=? ORDER BY created_at DESC LIMIT 30", (user["id"],))
    ids = [row["id"] for row in rows]
    artifacts: dict[str, list] = {job_id: [] for job_id in ids}
    if ids:
        for item in state.db.all(f"SELECT * FROM artifacts WHERE job_id IN ({','.join('?' * len(ids))}) ORDER BY created_at", tuple(ids)):
            artifacts[item["job_id"]].append(item)
    body = {
        "jobs": [job_out(row, artifacts[row["id"]], snapshot["positions"].get(row["id"])) for row in rows],
        "room": {key: snapshot[key] for key in ("queued_total", "running_total", "workers_online", "workers_busy")},
    }
    encoded = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode()
    etag = '"' + hashlib.sha256(encoded).hexdigest()[:32] + '"'
    headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
    if request.headers.get("if-none-match") == etag: return Response(status_code=304, headers=headers)
    return Response(encoded, media_type="application/json", headers=headers)


def used_bytes(state: Hub, user_id: str) -> int:
    uploads = state.db.one("SELECT COALESCE(SUM(expected_size),0) AS total FROM uploads WHERE user_id=?", (user_id,))["total"]
    outputs = state.db.one("SELECT COALESCE(SUM(size),0) AS total FROM artifacts WHERE user_id=?", (user_id,))["total"]
    return uploads + outputs


@router.post("/uploads")
def create_upload(payload: UploadCreate, user: dict = Depends(current_user), state: Hub = Depends(hub)):
    kind = INPUT_KINDS.get(payload.input_key)
    if not kind: raise HTTPException(422, "Tipo de archivo de entrada desconocido")
    if payload.size > state.settings.max_upload_mb * 1024 * 1024: raise HTTPException(413, f"El archivo supera el máximo de {state.settings.max_upload_mb} MB")
    if used_bytes(state, user["id"]) + payload.size > state.settings.user_quota_mb * 1024 * 1024:
        raise HTTPException(413, "Llegaste al espacio máximo. Borrá trabajos viejos para liberar lugar.")
    upload_id = uuid.uuid4().hex
    folder = state.uploads_dir / user["id"]; folder.mkdir(parents=True, exist_ok=True)
    name = Path(payload.name).name[:120] or "archivo"
    state.db.execute("INSERT INTO uploads (id, user_id, name, media_type, kind, expected_size, path, created_at) VALUES (?,?,?,?,?,?,?,?)",
                     (upload_id, user["id"], name, payload.media_type, kind, payload.size, str(folder / f"{upload_id}.bin"), time.time()))
    return {"id": upload_id, "chunk_bytes": CHUNK_BYTES}


def own_upload(state: Hub, upload_id: str, user: dict) -> dict:
    row = state.db.one("SELECT * FROM uploads WHERE id=? AND user_id=?", (upload_id, user["id"]))
    if not row: raise HTTPException(404, "Archivo inexistente")
    return row


@router.put("/uploads/{upload_id}/chunks/{index}")
async def upload_chunk(upload_id: str, index: int, request: Request, user: dict = Depends(current_user), state: Hub = Depends(hub)):
    row = own_upload(state, upload_id, user)
    if row["complete"]: raise HTTPException(409, "El archivo ya está completo")
    offset = index * CHUNK_BYTES
    if index < 0 or offset > row["received"] or offset >= row["expected_size"]: raise HTTPException(409, "Fragmento fuera de orden")
    limit = min(CHUNK_BYTES, row["expected_size"] - offset)
    path = Path(row["path"]); written = 0
    # Re-sending a chunk after a network error rewrites it instead of duplicating data.
    with path.open("r+b" if path.exists() else "wb") as target:
        target.truncate(offset); target.seek(offset)
        async for data in request.stream():
            written += len(data)
            if written > limit: raise HTTPException(413, "Fragmento demasiado grande")
            target.write(data)
    state.db.execute("UPDATE uploads SET received=? WHERE id=?", (offset + written, upload_id))
    return {"received": offset + written}


@router.post("/uploads/{upload_id}/complete")
def complete_upload(upload_id: str, user: dict = Depends(current_user), state: Hub = Depends(hub)):
    row = own_upload(state, upload_id, user)
    path = Path(row["path"])
    if row["received"] != row["expected_size"] or not path.exists() or path.stat().st_size != row["expected_size"]:
        raise HTTPException(409, "El archivo llegó incompleto")
    with path.open("rb") as source: detected = sniff_media(source.read(64))
    if row["kind"] not in detected:
        path.unlink(missing_ok=True); state.db.execute("DELETE FROM uploads WHERE id=?", (upload_id,))
        expected = {"image": "una imagen", "video": "un video", "audio": "un audio"}[row["kind"]]
        raise HTTPException(422, f"El archivo no es {expected} en un formato admitido")
    state.db.execute("UPDATE uploads SET complete=1 WHERE id=?", (upload_id,))
    return {"id": upload_id}


def validate_parameters(parameters: dict[str, Any], policy: dict) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in parameters.items():
        if value is None or value == "": continue
        if key not in ALLOWED_PARAMETERS: raise HTTPException(422, f"Parámetro no admitido: {key}")
        if isinstance(value, bool) or isinstance(value, (int, float)):
            if isinstance(value, float) and not math.isfinite(value): raise HTTPException(422, f"Valor inválido en {key}")
        elif isinstance(value, str):
            if len(value) > (500 if key == "negative_prompt" else 120): raise HTTPException(422, f"Texto demasiado largo en {key}")
        else:
            raise HTTPException(422, f"Valor inválido en {key}")
        clean[key] = value

    def number(key: str) -> float | None:
        value = clean.get(key)
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    if (resolution := clean.get("resolution")) is not None:
        match = re.fullmatch(r"(\d{2,4})x(\d{2,4})", str(resolution))
        if not match: raise HTTPException(422, "Resolución inválida")
        if int(match[1]) * int(match[2]) > policy["max_pixels"]: raise HTTPException(422, "La resolución supera el máximo permitido en la sala")
    limits = {"video_length": ("max_video_frames", "frames"), "num_inference_steps": ("max_steps", "pasos"),
              "duration_seconds": ("max_audio_seconds", "segundos de audio"), "batch_size": ("max_batch_size", "resultados por pedido")}
    for key, (policy_key, label) in limits.items():
        value = number(key)
        if value is not None and (value < 0 or value > policy[policy_key]): raise HTTPException(422, f"Máximo permitido: {policy[policy_key]} {label}")
    return clean


@router.post("/jobs")
async def create_job(payload: JobCreate, user: dict = Depends(current_user), state: Hub = Depends(hub)):
    policy = state.policy()
    if payload.model not in TASKS or payload.task not in TASKS[payload.model]: raise HTTPException(422, "El modelo no admite esa tarea")
    if payload.model not in policy["enabled_models"]: raise HTTPException(403, "Ese modelo no está habilitado en la sala")
    installed = set()
    for worker in state.db.all("SELECT installed_json FROM workers WHERE disabled=0"):
        installed.update(json.loads(worker["installed_json"] or "[]"))
    if payload.model not in installed: raise HTTPException(409, "Ninguna computadora de la sala tiene ese modelo instalado")
    if len(payload.prompt) > state.settings.max_prompt_chars: raise HTTPException(422, f"La instrucción supera los {state.settings.max_prompt_chars} caracteres")
    parameters = validate_parameters(payload.parameters, policy)
    inputs: dict[str, str | list[str]] = {}
    for key, value in payload.inputs.items():
        kind = INPUT_KINDS.get(key)
        ids = value if isinstance(value, list) else [value]
        if not kind or not ids or len(ids) > MAX_FILES_PER_INPUT: raise HTTPException(422, f"Entrada inválida: {key}")
        for upload_id in ids:
            row = state.db.one("SELECT kind, complete FROM uploads WHERE id=? AND user_id=?", (upload_id, user["id"]))
            if not row or not row["complete"] or row["kind"] != kind: raise HTTPException(422, f"Archivo inválido o incompleto en {key}")
        inputs[key] = value
    with state.db.transaction() as connection:
        active = connection.execute("SELECT COUNT(*) FROM jobs WHERE user_id=? AND status IN ('queued','running')", (user["id"],)).fetchone()[0]
        if user["role"] != "admin" and active >= state.settings.max_active_jobs_per_user:
            raise HTTPException(429, "Ya tenés un trabajo en curso. Esperá a que termine o cancelalo.")
        job_id = uuid.uuid4().hex; now = time.time()
        connection.execute(
            "INSERT INTO jobs (id, user_id, model, task, prompt, inputs_json, parameters_json, status, progress, phase, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (job_id, user["id"], payload.model, payload.task, payload.prompt, json.dumps(inputs), json.dumps(parameters), "queued", 0, "queued", now, now))
    state.notify_workers()
    snapshot = state.scheduler.queue_snapshot()
    return job_out(state.db.one("SELECT * FROM jobs WHERE id=?", (job_id,)), [], snapshot["positions"].get(job_id))


def own_job(state: Hub, job_id: str, user: dict) -> dict:
    row = state.db.one("SELECT * FROM jobs WHERE id=?", (job_id,))
    if not row or (row["user_id"] != user["id"] and user["role"] != "admin"): raise HTTPException(404, "Trabajo inexistente")
    return row


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, user: dict = Depends(current_user), state: Hub = Depends(hub)):
    own_job(state, job_id, user)
    state.scheduler.cancel(job_id)
    return {"ok": True}


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str, user: dict = Depends(current_user), state: Hub = Depends(hub)):
    row = own_job(state, job_id, user)
    if row["status"] in ("queued", "running"): raise HTTPException(409, "Cancelá el trabajo antes de borrarlo")
    remove_job_files(state, job_id)
    state.db.execute("DELETE FROM jobs WHERE id=?", (job_id,))
    return {"ok": True}


def remove_job_files(state: Hub, job_id: str) -> None:
    for artifact in state.db.all("SELECT path FROM artifacts WHERE job_id=?", (job_id,)):
        Path(artifact["path"]).unlink(missing_ok=True)
    folder = state.outputs_dir / job_id
    if folder.exists():
        for item in folder.iterdir(): item.unlink(missing_ok=True)
        folder.rmdir()


@router.get("/files/{artifact_id}")
def get_file(artifact_id: str, download: bool = False, user: dict = Depends(current_user), state: Hub = Depends(hub)):
    artifact = state.db.one("SELECT * FROM artifacts WHERE id=?", (artifact_id,))
    if not artifact or (artifact["user_id"] != user["id"] and user["role"] != "admin") or not os.path.exists(artifact["path"]):
        raise HTTPException(404, "Archivo inexistente")
    return FileResponse(artifact["path"], media_type=artifact["media_type"], filename=artifact["name"],
                        content_disposition_type="attachment" if download else "inline",
                        headers={"Cache-Control": "private, max-age=86400", "Content-Security-Policy": "default-src 'none'; sandbox"})
