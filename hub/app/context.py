import asyncio
import ipaddress
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from fastapi import Depends, HTTPException, Request
from .catalog import DEFAULT_POLICY
from .config import HubSettings
from .db import Database
from .scheduler import Scheduler
from .security import RateLimiter, token_hash

LOOPBACK = {"127.0.0.1", "::1"}


@dataclass
class Hub:
    settings: HubSettings
    db: Database
    scheduler: Scheduler
    login_limiter: RateLimiter
    register_limiter: RateLimiter
    wake: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def uploads_dir(self) -> Path: return self.settings.data_dir / "uploads"

    @property
    def outputs_dir(self) -> Path: return self.settings.data_dir / "outputs"

    @property
    def cookie_name(self) -> str:
        # The __Host- prefix makes browsers refuse the cookie unless it is Secure, host-only and Path=/.
        return "__Host-lv_session" if self.settings.secure_cookies else "lv_session"

    def notify_workers(self) -> None:
        self.wake.set()
        self.wake = asyncio.Event()

    def policy(self) -> dict:
        row = self.db.one("SELECT value FROM settings_kv WHERE key='policy'")
        stored = json.loads(row["value"]) if row else {}
        return {**DEFAULT_POLICY, **stored}

    def save_policy(self, policy: dict) -> None:
        self.db.execute("INSERT INTO settings_kv (key, value) VALUES ('policy', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(policy),))


def hub(request: Request) -> Hub:
    return request.app.state.hub


def peer_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def via_tunnel(request: Request) -> bool:
    """Cloudflare always adds these headers at its edge; a request carrying them came through the tunnel."""
    return peer_ip(request) in LOOPBACK and ("cf-connecting-ip" in request.headers or "cf-ray" in request.headers)


def client_ip(request: Request) -> str:
    if via_tunnel(request):
        return request.headers.get("cf-connecting-ip", "").strip() or peer_ip(request)
    return peer_ip(request)


def in_networks(ip: str, networks) -> bool:
    if not networks: return True
    try: address = ipaddress.ip_address(ip)
    except ValueError: return False
    return any(address in network for network in networks)


def current_user(request: Request, state: Hub = Depends(hub)) -> dict:
    token = request.cookies.get(state.cookie_name)
    if not token: raise HTTPException(401, "Iniciá sesión para continuar")
    row = state.db.one(
        "SELECT u.*, s.expires_at AS session_expires_at FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash=?",
        (token_hash(token),),
    )
    if not row or row["session_expires_at"] < time.time() or row["disabled"]:
        raise HTTPException(401, "La sesión venció. Iniciá sesión de nuevo")
    return row


def admin_user(request: Request, user: dict = Depends(current_user), state: Hub = Depends(hub)) -> dict:
    if user["role"] != "admin": raise HTTPException(403, "Solo para administración")
    if state.settings.mode == "tunnel" and via_tunnel(request):
        raise HTTPException(403, "El panel de administración solo se usa desde la red del laboratorio")
    ip = client_ip(request)
    local = ip in LOOPBACK and not via_tunnel(request)
    if not local and not in_networks(ip, state.settings.admin_network_list):
        raise HTTPException(403, "El panel de administración no está habilitado desde esta red")
    return user


def current_worker(request: Request, state: Hub = Depends(hub)) -> dict:
    if via_tunnel(request): raise HTTPException(403, "La API de workers no se publica por el túnel")
    # The hub PC is also a GPU worker; its own agent connects over loopback.
    if peer_ip(request) not in LOOPBACK and not in_networks(peer_ip(request), state.settings.worker_network_list):
        raise HTTPException(403, "Red no autorizada para workers")
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token: raise HTTPException(401, "Falta el token del worker")
    worker = state.db.one("SELECT * FROM workers WHERE token_hash=?", (token_hash(token.strip()),))
    if not worker or worker["disabled"]: raise HTTPException(401, "Token de worker inválido")
    return worker
