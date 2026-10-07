from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    """Lab PC agent configuration, read from LOCALVIA_WORKER_<NAME> or worker/.env."""

    model_config = SettingsConfigDict(env_prefix="LOCALVIA_WORKER_", env_file=("worker/.env",), extra="ignore")

    hub_url: str = "https://127.0.0.1:8443"
    token: str = ""
    # PEM file used to verify the hub certificate (the self-signed hub.crt in LAN mode). Empty = system store.
    ca_file: Path | None = None

    data_dir: Path = Path("data/worker")
    backend: str = "mock"
    wangp_root: Path = Path(".runtime/Wan2GP")
    wangp_cli_args: str = "--attention sdpa --profile 4 --perc-reserved-mem-max 0.25"
    wangp_preload_mb: int = 4000
    model_idle_timeout_seconds: int = 3600

    # Do not take new work while the GPU is at or above this temperature (0 disables the guard).
    max_gpu_temp_c: int = 85
    heartbeat_seconds: float = 5.0

    # Mock backend only: simulated duration and optional folder with sample outputs (image.*, video.*, audio.*).
    mock_seconds: float = 0.6
    mock_samples_dir: Path | None = None


settings = WorkerSettings()
