import ipaddress
from pathlib import Path
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class HubSettings(BaseSettings):
    """Hub configuration. Every value can be set as LOCALVIA_HUB_<NAME> in hub/.env."""

    model_config = SettingsConfigDict(env_prefix="LOCALVIA_HUB_", env_file=("hub/.env",), extra="ignore")

    # "lan": students reach the hub directly (campus network or university VPN).
    # "tunnel": students arrive through a Cloudflare Tunnel that connects to 127.0.0.1.
    mode: Literal["lan", "tunnel"] = "lan"
    host: str = "0.0.0.0"
    port: int = 8443
    tls_cert_file: Path | None = None
    tls_key_file: Path | None = None

    data_dir: Path = Path("data/hub")
    ui_dir: Path = Path("out")

    # Networks allowed to use the worker API (lab subnet). Empty = any address that holds a worker token.
    worker_networks: str = ""
    # Networks allowed to open the admin panel. In tunnel mode admin is never served through the tunnel.
    admin_networks: str = ""

    session_hours: int = 12
    max_upload_mb: int = 200
    max_output_mb: int = 2048
    user_quota_mb: int = 2048
    max_active_jobs_per_user: int = 1
    retention_days: int = 14
    max_prompt_chars: int = 4000

    lease_seconds: int = 90
    max_job_attempts: int = 2
    worker_offline_seconds: int = 45
    claim_wait_seconds: int = 20
    # A worker that already has a model in VRAM may take a younger job for that model
    # if it entered the queue less than this many seconds after the oldest job.
    affinity_window_seconds: int = 300

    login_max_failures: int = 5
    login_window_minutes: int = 15

    @property
    def https(self) -> bool:
        return self.tls_cert_file is not None and self.tls_key_file is not None

    @property
    def secure_cookies(self) -> bool:
        # Cloudflare terminates TLS in tunnel mode, so the browser always sees HTTPS.
        return self.https or self.mode == "tunnel"

    @staticmethod
    def _networks(value: str) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        return [ipaddress.ip_network(item.strip(), strict=False) for item in value.split(",") if item.strip()]

    @property
    def worker_network_list(self): return self._networks(self.worker_networks)

    @property
    def admin_network_list(self): return self._networks(self.admin_networks)


settings = HubSettings()
