"""Starts the hub: `python -m hub` from the repository root."""
import uvicorn
from hub.app.config import settings
from hub.app.main import create_app

if __name__ == "__main__":
    if settings.mode == "tunnel" and settings.host not in ("127.0.0.1", "::1") and not settings.worker_networks:
        print("Aviso: en modo túnel conviene limitar LOCALVIA_HUB_WORKER_NETWORKS a la subred del laboratorio.")
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        ssl_certfile=str(settings.tls_cert_file) if settings.https else None,
        ssl_keyfile=str(settings.tls_key_file) if settings.https else None,
        # The hub decides itself which proxy headers to trust (only Cloudflare's, only from loopback).
        proxy_headers=False,
        server_header=False,
        timeout_keep_alive=30,
        log_level="info",
    )
