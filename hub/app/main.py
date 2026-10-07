import asyncio
import contextlib
import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from .config import HubSettings, settings as default_settings
from .context import Hub
from .db import Database
from .routes_admin import router as admin_router
from .routes_student import remove_job_files, router as student_router
from .routes_worker import router as worker_router
from .scheduler import Scheduler
from .security import RateLimiter

log = logging.getLogger("localvia.hub")
JSON_BODY_LIMIT = 1024 * 1024
STREAMING_ROUTES = ("/chunks/", "/artifacts")


def security_headers(https: bool) -> dict[str, str]:
    headers = {
        # Next.js static export inlines its bootstrap scripts, so 'unsafe-inline' is required for scripts;
        # everything else, including network access, is restricted to this same origin.
        "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
                                   "img-src 'self' data: blob:; media-src 'self' blob:; font-src 'self' data:; connect-src 'self'; "
                                   "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-origin",
    }
    if https: headers["Strict-Transport-Security"] = "max-age=31536000"
    return headers


class SelectiveGZip:
    """Compresses JSON and UI assets, but never media files or streaming worker transfers."""

    def __init__(self, app):
        self.app, self.gzip = app, GZipMiddleware(app, minimum_size=800)

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "") if scope["type"] == "http" else ""
        if scope["type"] == "http" and not path.startswith(("/api/files/", "/worker-api/")):
            await self.gzip(scope, receive, send)
        else:
            await self.app(scope, receive, send)


def cleanup_expired(state: Hub) -> None:
    now = time.time()
    state.db.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
    cutoff = now - state.settings.retention_days * 86400
    for job in state.db.all("SELECT id FROM jobs WHERE status NOT IN ('queued','running') AND COALESCE(finished_at, updated_at) < ?", (cutoff,)):
        remove_job_files(state, job["id"])
        state.db.execute("DELETE FROM jobs WHERE id=?", (job["id"],))
    # Inputs are kept while a job may still need them, and removed with the retention window.
    active_inputs = {item for row in state.db.all("SELECT inputs_json FROM jobs WHERE status IN ('queued','running')") for item in _ids(row["inputs_json"])}
    for upload in state.db.all("SELECT id, path, complete, created_at FROM uploads WHERE created_at < ?", (now - 86400,)):
        if upload["id"] in active_inputs: continue
        if not upload["complete"] or upload["created_at"] < cutoff:
            Path(upload["path"]).unlink(missing_ok=True)
            state.db.execute("DELETE FROM uploads WHERE id=?", (upload["id"],))
    state.db.execute("DELETE FROM audit WHERE at < ?", (now - 365 * 86400,))


def _ids(inputs_json: str) -> list[str]:
    return [item for value in json.loads(inputs_json).values() for item in (value if isinstance(value, list) else [value])]


async def maintenance(state: Hub) -> None:
    last_cleanup = 0.0
    while True:
        try:
            if state.scheduler.reap(): state.notify_workers()
            if time.time() - last_cleanup > 3600:
                cleanup_expired(state); last_cleanup = time.time()
        except Exception:
            log.exception("maintenance failed")
        await asyncio.sleep(5)


def create_app(settings: HubSettings | None = None) -> FastAPI:
    settings = settings or default_settings
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    db = Database(settings.data_dir / "hub.db")
    window = settings.login_window_minutes * 60
    state = Hub(settings, db, Scheduler(db, settings), RateLimiter(settings.login_max_failures, window), RateLimiter(10, window))

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        task = asyncio.create_task(maintenance(state))
        yield
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError): await task

    app = FastAPI(title="Local Via Hub", version="1.0.0", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.hub = state
    headers = security_headers(settings.https or settings.mode == "tunnel")

    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            length = request.headers.get("content-length")
            if not any(marker in path for marker in STREAMING_ROUTES) and length and int(length) > JSON_BODY_LIMIT:
                return JSONResponse({"detail": "Pedido demasiado grande"}, status_code=413, headers=headers)
            if path.startswith("/api/"):
                # CSRF defence: browsers cannot add a custom header cross-site without a CORS preflight,
                # and this server never answers preflights. Sec-Fetch-Site rejects cross-site forms too.
                site = request.headers.get("sec-fetch-site")
                if request.headers.get("x-localvia") != "1" or (site and site not in ("same-origin", "none")):
                    return JSONResponse({"detail": "Pedido rechazado"}, status_code=403, headers=headers)
        response = await call_next(request)
        for key, value in headers.items(): response.headers.setdefault(key, value)
        if path.startswith("/api/") and "cache-control" not in response.headers: response.headers["Cache-Control"] = "no-store"
        return response

    app.add_middleware(SelectiveGZip)
    app.include_router(student_router)
    app.include_router(admin_router)
    app.include_router(worker_router)

    @app.get("/healthz")
    def health(): return {"ok": True}

    if (settings.ui_dir / "index.html").exists():
        app.mount("/", StaticFiles(directory=settings.ui_dir, html=True), name="ui")
    else:
        @app.get("/", response_class=HTMLResponse)
        def missing_ui(): return "<h1>Local Via</h1><p>Falta compilar la interfaz: ejecutá <code>npm run build</code>.</p>"

    return app
