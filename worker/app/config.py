from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOCAL_VIA_", env_file=("worker/.env", ".env"), extra="ignore")

    worker_id: str = "aula-pc-01"
    token: str = "local-via-change-me"
    signing_secret: str = "local-via-signing-change-me"
    data_dir: Path = Path("data")
    wangp_root: Path = Path(".runtime/Wan2GP")
    backend: str = "mock"
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    public_base_url: str = ""
    wangp_cli_args: str = "--attention sdpa --profile 4"
    wangp_preload_mb: int = 4000
    model_idle_timeout_seconds: int = 3600

    @property
    def origins(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]


settings = Settings()
