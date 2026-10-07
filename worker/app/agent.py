"""Lab PC agent. It only opens outbound connections to the hub: no port is exposed on the worker."""
import asyncio
import logging
import re
import shutil
import ssl
import time
from pathlib import Path
from typing import Any
import httpx
from .backends import JobCancelled, MockBackend, WanGPBackend
from .config import WorkerSettings

log = logging.getLogger("localvia.worker")
VERSION = "1.0.0"
INSTALLED_REFRESH_SECONDS = 600


def gpu_info() -> dict | None:
    try:
        import pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
        name = pynvml.nvmlDeviceGetName(handle)
        return {"name": name.decode() if isinstance(name, bytes) else name, "vram_total_mb": memory.total // 1048576,
                "vram_free_mb": memory.free // 1048576, "temperature_c": pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)}
    except Exception:
        return None


def build_backend(settings: WorkerSettings):
    if settings.backend == "wangp":
        cli_args = settings.wangp_cli_args.split()
        if settings.wangp_preload_mb > 0 and "--preload" not in cli_args: cli_args += ["--preload", str(settings.wangp_preload_mb)]
        return WanGPBackend(settings.wangp_root, settings.data_dir / "wangp-outputs", cli_args, settings.model_idle_timeout_seconds, settings.wangp_preload_mb)
    return MockBackend(settings.data_dir / "mock-outputs", settings.mock_seconds, settings.mock_samples_dir)


class Agent:
    def __init__(self, settings: WorkerSettings, backend=None, transport: httpx.AsyncBaseTransport | None = None):
        if not settings.token: raise SystemExit("Falta LOCALVIA_WORKER_TOKEN en worker/.env (lo genera el hub con add-worker).")
        # WanGP changes the working directory when it starts, so every path is made absolute first.
        settings.data_dir = settings.data_dir.resolve()
        settings.wangp_root = settings.wangp_root.resolve()
        if settings.ca_file: settings.ca_file = settings.ca_file.resolve()
        if settings.mock_samples_dir: settings.mock_samples_dir = settings.mock_samples_dir.resolve()
        self.settings = settings
        self.backend = backend or build_backend(settings)
        self.transport = transport
        self.stopping = asyncio.Event()
        self.installed: list[str] = []
        self.installed_at = 0.0

    def _client(self) -> httpx.AsyncClient:
        verify: Any = True
        if self.settings.ca_file:
            verify = ssl.create_default_context(cafile=str(self.settings.ca_file))
        return httpx.AsyncClient(base_url=self.settings.hub_url.rstrip("/"), verify=verify, transport=self.transport,
                                 headers={"Authorization": f"Bearer {self.settings.token}", "User-Agent": f"local-via-worker/{VERSION}"},
                                 timeout=httpx.Timeout(60.0, connect=10.0))

    async def _installed_models(self) -> list[str]:
        if not self.installed or time.time() - self.installed_at > INSTALLED_REFRESH_SECONDS:
            availability = await asyncio.to_thread(self.backend.availability)
            self.installed = sorted(model for model, ok in availability.items() if ok)
            self.installed_at = time.time()
        return self.installed

    async def state(self) -> dict:
        return {"backend": self.backend.name, "version": VERSION, "loaded_model": getattr(self.backend, "loaded_model", None),
                "gpu": gpu_info(), "installed_models": await self._installed_models()}

    async def run(self) -> None:
        backoff = 1.0
        async with self._client() as client:
            while not self.stopping.is_set():
                try:
                    state = await self.state()
                    temperature = (state.get("gpu") or {}).get("temperature_c")
                    if self.settings.max_gpu_temp_c and temperature and temperature >= self.settings.max_gpu_temp_c:
                        log.warning("GPU a %s °C: espero a que baje antes de aceptar trabajo", temperature)
                        await self._sleep(15); continue
                    response = await client.post("/worker-api/claim", json={"state": state}, timeout=httpx.Timeout(90.0, connect=10.0))
                    if response.status_code == 204: backoff = 1.0; continue
                    if response.status_code in (401, 403):
                        log.error("El hub rechazó al worker (%s): %s", response.status_code, response.text[:200])
                        await self._sleep(30); continue
                    response.raise_for_status()
                    backoff = 1.0
                    await self.process(client, response.json())
                except (httpx.TransportError, httpx.HTTPStatusError) as error:
                    log.warning("Sin conexión con el hub (%s). Reintento en %.0f s", error, backoff)
                    await self._sleep(backoff); backoff = min(backoff * 2, 30.0)

    async def _sleep(self, seconds: float) -> None:
        try: await asyncio.wait_for(self.stopping.wait(), timeout=seconds)
        except asyncio.TimeoutError: pass

    async def process(self, client: httpx.AsyncClient, job: dict) -> None:
        job_id = job["id"]
        workdir = self.settings.data_dir / "jobs" / job_id
        status = {"progress": 1, "phase": "downloading_inputs"}
        cancelled = asyncio.Event()
        log.info("Trabajo %s: %s / %s", job_id, job["model"], job["task"])

        def report(value: int, phase: str) -> None:
            if value >= 0: status["progress"] = value
            if phase: status["phase"] = phase

        async def heartbeat() -> None:
            while True:
                try:
                    response = await client.post(f"/worker-api/jobs/{job_id}/progress", json=status, timeout=20)
                    if response.status_code == 409 or (response.is_success and response.json().get("cancel")):
                        if not cancelled.is_set():
                            cancelled.set(); self.backend.cancel()
                except httpx.HTTPError as error:
                    log.warning("No se pudo informar el progreso: %s", error)
                await asyncio.sleep(self.settings.heartbeat_seconds)

        beat = asyncio.create_task(heartbeat())
        outcome, error_text = "failed", None
        outputs: list[Path] = []
        try:
            inputs = await self._download_inputs(client, job, workdir / "inputs")
            report(2, "loading")
            payload = {"id": job_id, "model": job["model"], "task": job["task"], "prompt": job["prompt"], "parameters": job["parameters"]}
            outputs = await self.backend.execute(payload, inputs, report)
            if cancelled.is_set(): raise JobCancelled()
            report(-1, "uploading_output")
            for path in outputs:
                if path.exists(): await self._upload(client, job_id, path)
            outcome = "succeeded"
        except JobCancelled:
            outcome = "cancelled"
        except Exception as error:  # the hub shows this message to the student
            outcome = "cancelled" if cancelled.is_set() else "failed"
            error_text = str(error)[:2000] or error.__class__.__name__
            log.exception("Trabajo %s falló", job_id)
        finally:
            beat.cancel()
            try: await client.post(f"/worker-api/jobs/{job_id}/complete", json={"status": outcome, "error": error_text}, timeout=30)
            except httpx.HTTPError as error: log.warning("No se pudo cerrar el trabajo %s: %s", job_id, error)
            # Student inputs and outputs live on the hub only; nothing is kept on the lab PC.
            shutil.rmtree(workdir, ignore_errors=True)
            for path in outputs: path.unlink(missing_ok=True)
            self.installed_at = 0.0
        log.info("Trabajo %s: %s", job_id, outcome)

    async def _download_inputs(self, client: httpx.AsyncClient, job: dict, folder: Path) -> dict[str, Path | list[Path]]:
        folder.mkdir(parents=True, exist_ok=True)
        resolved: dict[str, Path | list[Path]] = {}
        for key, files in job["inputs"].items():
            paths = []
            for index, item in enumerate(files):
                suffix = re.sub(r"[^a-z0-9.]", "", Path(item["name"]).suffix.lower())[:8]
                target = folder / f"{key}_{index}{suffix}"
                async with client.stream("GET", f"/worker-api/jobs/{job['id']}/inputs/{item['id']}") as response:
                    response.raise_for_status()
                    with target.open("wb") as handle:
                        async for chunk in response.aiter_bytes(1024 * 1024): handle.write(chunk)
                paths.append(target)
            resolved[key] = paths if job.get("input_is_list", {}).get(key) else paths[0]
        return resolved

    async def _upload(self, client: httpx.AsyncClient, job_id: str, path: Path) -> None:
        async def body():
            with path.open("rb") as handle:
                while chunk := await asyncio.to_thread(handle.read, 1024 * 1024): yield chunk
        response = await client.put(f"/worker-api/jobs/{job_id}/artifacts", params={"name": path.name}, content=body(),
                                    headers={"Content-Type": "application/octet-stream", "Content-Length": str(path.stat().st_size)}, timeout=300)
        response.raise_for_status()
