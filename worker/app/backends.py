import asyncio
import contextlib
import hashlib
import os
import shutil
import struct
import sys
import threading
import time
import wave
import zlib
from pathlib import Path
from typing import Callable
from .catalog import MODEL_VARIANTS, TASKS


Progress = Callable[[int, str], None]


class JobCancelled(Exception):
    """Raised by a backend when the current job was cancelled."""


def _png(path: Path, rgb: tuple[int, int, int], size: int = 256) -> None:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    row = b"\x00" + bytes(rgb) * size
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(row * size)) + chunk(b"IEND", b""))


def _wav(path: Path, seconds: float = 1.0, rate: int = 16000) -> None:
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1); target.setsampwidth(2); target.setframerate(rate)
        target.writeframes(b"\x00\x00" * int(seconds * rate))


class MockBackend:
    """Deterministic stand-in for WanGP: no GPU, configurable duration and optional real sample outputs."""
    name = "mock"
    ready = True

    def __init__(self, output_dir: Path, seconds: float = 0.6, samples_dir: Path | None = None):
        self.output_dir, self.seconds, self.samples_dir = output_dir, seconds, samples_dir
        self.cancelled = threading.Event()
        self.loaded_model: str | None = None

    def availability(self) -> dict[str, bool]: return {model_id: True for model_id in TASKS}

    def _sample(self, kind: str) -> Path | None:
        if not self.samples_dir or not self.samples_dir.is_dir(): return None
        return next(iter(sorted(self.samples_dir.glob(f"{kind}.*"))), None)

    async def execute(self, job: dict, inputs: dict[str, Path | list[Path]], progress: Progress) -> list[Path]:
        self.cancelled.clear()
        steps = 5
        for step in range(1, steps + 1):
            if self.cancelled.is_set(): raise JobCancelled()
            await asyncio.sleep(self.seconds / steps); progress(step * 18, "inference")
        self.loaded_model = job["model"]
        target = self.output_dir / job["id"]
        target.mkdir(parents=True, exist_ok=True)
        family = job["task"].split(".", 1)[0]
        kind = "image" if family == "image" else "video" if family in ("video", "character") else "audio"
        sample = self._sample(kind)
        if sample:
            output = target / f"{kind}{sample.suffix.lower()}"
            shutil.copyfile(sample, output)
        elif kind == "audio":
            output = target / "audio.wav"; _wav(output)
        else:
            digest = hashlib.sha256((job.get("prompt") or job["model"]).encode()).digest()
            output = target / f"{kind}.png"; _png(output, (digest[0], digest[1], digest[2]))
        progress(100, "complete")
        return [output]

    def cancel(self) -> None: self.cancelled.set()


class WanGPBackend:
    name = "wangp"

    def __init__(self, root: Path, output_dir: Path, cli_args: list[str], idle_timeout_seconds: int = 3600, preload_mb: int = 0):
        self.root, self.output_dir, self.cli_args = root.resolve(), output_dir.resolve(), cli_args
        self.session = None
        self.current_job = None
        self.lock = threading.Lock()
        self.execution_lock = threading.Lock()
        self.idle_lock = threading.Lock()
        self.idle_timeout_seconds = max(0, idle_timeout_seconds)
        self.preload_mb = max(0, preload_mb)
        self.idle_timer: threading.Timer | None = None
        self.idle_generation = 0
        self.loaded_model: str | None = None
        self.last_used_at: float | None = None

    @property
    def ready(self) -> bool: return (self.root / "shared" / "api.py").exists()

    def _session(self):
        with self.lock:
            if self.session is None:
                if not self.ready: raise RuntimeError(f"WanGP no está instalado en {self.root}")
                sys.path.insert(0, str(self.root)) if str(self.root) not in sys.path else None
                os.chdir(self.root)
                from shared.api import init
                self.session = init(root=self.root, output_dir=self.output_dir, cli_args=self.cli_args, console_output=True)
            return self.session

    def availability(self) -> dict[str, bool]:
        if not self.ready: return {}
        try:
            session = self._session()
            availability = {row["model_type"]: bool(row.get("available")) for row in session.list_model_availability()}
            for model_id, variant in MODEL_VARIANTS.items():
                base_available = availability.get(variant["base_model"], False)
                files_available = all((self.root / path).is_file() for path in variant.get("required_files", ()))
                availability[model_id] = base_available and files_available
            return availability
        except Exception: return {}

    async def execute(self, job: dict, inputs: dict[str, Path | list[Path]], progress: Progress) -> list[Path]:
        return await asyncio.to_thread(self._execute_sync, job, inputs, progress)

    def _execute_sync(self, job: dict, inputs: dict[str, Path | list[Path]], progress: Progress) -> list[Path]:
        self._cancel_idle_release()
        try:
            with self.execution_lock:
                return self._execute_sync_locked(job, inputs, progress)
        except BaseException:
            # A failed native CUDA kernel can leave the loaded model/context in an
            # unusable state. Never advertise or retain that model as a warm cache.
            with self.execution_lock:
                if self.session is not None:
                    with contextlib.suppress(Exception):
                        self.session.close()
                self.loaded_model = None
            raise
        finally:
            self.last_used_at = time.time()
            if self.loaded_model is not None:
                self._schedule_idle_release()

    def _execute_sync_locked(self, job: dict, inputs: dict[str, Path | list[Path]], progress: Progress) -> list[Path]:
        session = self._session()
        if job["task"] == "audio.convert":
            source = inputs.get("audio_source")
            reference = inputs.get("voice_reference")
            if not isinstance(source, Path) or not isinstance(reference, Path): raise ValueError("SeedVC requiere audio original y voz destino")
            api_job = session.submit_audio_postprocessing(str(source), postprocess_audio="seedvc_one_speaker", replace_voice_sample=str(reference))
        else:
            variant = MODEL_VARIANTS.get(job["model"])
            model_type = variant["base_model"] if variant else job["model"]
            settings = session.get_default_settings(model_type) or {}
            parameters = {key: value for key, value in job["parameters"].items() if value is not None}
            mode_parts = [parameters.pop(key, "") for key in ("guide_preprocess", "mask_preprocess", "image_ref_mode")]
            settings.update(parameters)
            if variant:
                settings.update(variant["overrides"])
            if any(str(value) for value in mode_parts):
                settings["video_prompt_type"] = "".join(str(value) for value in mode_parts if value is not None)
            settings.update({"model_type": model_type, "prompt": job.get("prompt", "")})
            self._bind_inputs(model_type, settings, inputs)

            class Callbacks:
                def on_progress(self, update): progress(int(update.progress), str(update.phase))
                def on_status(self, status): progress(-1, str(status))
            api_job = session.submit_task(settings, callbacks=Callbacks())
        self.loaded_model = job["model"]
        self.current_job = api_job
        try:
            result = api_job.result()
        finally:
            self.current_job = None
        if not result.success:
            message = "; ".join(error.message for error in result.errors) or "WanGP generation failed"
            raise RuntimeError(message)
        return [Path(path) for path in result.generated_files]

    @staticmethod
    def _bind_inputs(model: str, settings: dict, inputs: dict[str, Path | list[Path]]) -> None:
        """Bind explicit WanGP media roles without guessing semantics from MIME types."""
        allowed = {
            "image_start", "image_end", "image_refs", "image_guide", "image_mask",
            "video_source", "video_guide", "video_refs", "video_mask",
            "audio_guide", "audio_guide2",
        }
        aliases = {"video_source": "video_guide", "video_refs": "video_guide"}
        primary = inputs.get("image_primary")
        references = inputs.get("image_refs")
        if primary is not None:
            primary_path = primary[0] if isinstance(primary, list) else primary
            reference_paths = references if isinstance(references, list) else ([references] if references is not None else [])
            settings["image_refs"] = [str(primary_path), *(str(path) for path in reference_paths)]
        for role, value in inputs.items():
            if role == "image_primary" or (role == "image_refs" and primary is not None) or role not in allowed:
                continue
            target = aliases.get(role, role)
            if role == "video_refs" and isinstance(value, list):
                settings["video_guide"] = str(value[0])
                if len(value) > 1:
                    settings["video_guide2"] = str(value[1])
                continue
            if isinstance(value, list):
                rendered = [str(path) for path in value]
                settings[target] = rendered if target == "image_refs" else rendered[0]
            else:
                settings[target] = str(value)

    def _cancel_idle_release(self) -> None:
        with self.idle_lock:
            self.idle_generation += 1
            if self.idle_timer is not None:
                self.idle_timer.cancel()
                self.idle_timer = None

    def _schedule_idle_release(self) -> None:
        if self.idle_timeout_seconds <= 0:
            return
        with self.idle_lock:
            self.idle_generation += 1
            generation = self.idle_generation
            timer = threading.Timer(self.idle_timeout_seconds, self._release_after_idle, args=(generation,))
            timer.daemon = True
            self.idle_timer = timer
            timer.start()

    def _release_after_idle(self, generation: int) -> None:
        with self.execution_lock:
            with self.idle_lock:
                if generation != self.idle_generation or self.current_job is not None:
                    return
                self.idle_timer = None
            if self.session is not None:
                self.session.close()
            self.loaded_model = None

    def cache_status(self) -> dict[str, str | int | float | None]:
        idle_for = None if self.last_used_at is None else max(0.0, time.time() - self.last_used_at)
        return {
            "loaded_model": self.loaded_model,
            "idle_timeout_seconds": self.idle_timeout_seconds,
            "idle_for_seconds": idle_for,
            "preload_mb": self.preload_mb,
        }

    def cancel(self) -> None:
        if self.current_job is not None: self.current_job.cancel()
