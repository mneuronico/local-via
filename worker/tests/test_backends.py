from pathlib import Path

from worker.app.backends import WanGPBackend


def test_primary_image_is_bound_before_additional_references(tmp_path: Path):
    settings = {}
    WanGPBackend._bind_inputs(
        "qwen_image_edit_plus_20B",
        settings,
        {
            "image_refs": [tmp_path / "person.png", tmp_path / "object.png"],
            "image_primary": tmp_path / "scene.png",
        },
    )

    assert settings["image_refs"] == [
        str(tmp_path / "scene.png"),
        str(tmp_path / "person.png"),
        str(tmp_path / "object.png"),
    ]


def test_reference_only_modes_keep_their_original_order(tmp_path: Path):
    settings = {}
    references = [tmp_path / "a.png", tmp_path / "b.png"]
    WanGPBackend._bind_inputs("vace_14B", settings, {"image_refs": references})

    assert settings["image_refs"] == [str(path) for path in references]


def test_idle_release_unloads_the_cached_model(tmp_path: Path):
    class FakeSession:
        closed = False

        def close(self):
            self.closed = True

    backend = WanGPBackend(tmp_path, tmp_path / "outputs", [], idle_timeout_seconds=3600)
    session = FakeSession()
    backend.session = session
    backend.loaded_model = "z_image"
    backend.idle_generation = 4

    backend._release_after_idle(4)

    assert session.closed is True
    assert backend.loaded_model is None


def test_idle_timer_keeps_model_warm_then_releases_it(tmp_path: Path):
    import time

    class FakeSession:
        closed = False

        def close(self):
            self.closed = True

    backend = WanGPBackend(tmp_path, tmp_path / "outputs", [], idle_timeout_seconds=0.05, preload_mb=4000)
    session = FakeSession()
    backend.session = session
    backend.loaded_model = "ti2v_2_2_fastwan"
    backend.last_used_at = time.time()

    backend._schedule_idle_release()
    assert backend.loaded_model == "ti2v_2_2_fastwan"
    time.sleep(0.12)

    assert session.closed is True
    assert backend.loaded_model is None
    assert backend.cache_status()["preload_mb"] == 4000


def test_failed_generation_is_not_kept_as_a_warm_model(tmp_path: Path):
    class FakeSession:
        closed = False

        def close(self):
            self.closed = True

    backend = WanGPBackend(tmp_path, tmp_path / "outputs", [], idle_timeout_seconds=3600)
    session = FakeSession()
    backend.session = session
    backend.loaded_model = "qwen_image_edit_plus_20B_nunchaku_r128_int4"

    def fail(*_args):
        raise RuntimeError("CUDA error: unspecified launch failure")

    backend._execute_sync_locked = fail

    try:
        backend._execute_sync({"id": "failed"}, {}, lambda *_args: None)
    except RuntimeError:
        pass
    else:
        raise AssertionError("the simulated CUDA failure should propagate")

    assert session.closed is True
    assert backend.loaded_model is None
    assert backend.idle_timer is None


def test_lightning_variant_uses_base_model_and_locked_accelerator_settings(tmp_path: Path):
    class FakeResult:
        success = True
        generated_files = []
        errors = []

    class FakeJob:
        def result(self):
            return FakeResult()

    class FakeSession:
        submitted = None

        def get_default_settings(self, model):
            assert model == "qwen_image_edit_plus_20B"
            return {"num_inference_steps": 20, "guidance_scale": 4}

        def submit_task(self, settings, callbacks=None):
            self.submitted = settings
            return FakeJob()

    backend = WanGPBackend(tmp_path, tmp_path / "outputs", [])
    session = FakeSession()
    backend.session = session
    job = {
        "model": "qwen_image_edit_plus_20B_lightning_8",
        "task": "image.edit",
        "prompt": "change the sky",
        "parameters": {"num_inference_steps": 99, "guidance_scale": 9, "resolution": "512x512"},
    }

    backend._execute_sync_locked(job, {}, lambda *_args: None)

    assert session.submitted["model_type"] == "qwen_image_edit_plus_20B"
    assert session.submitted["num_inference_steps"] == 8
    assert session.submitted["guidance_scale"] == 1
    assert session.submitted["loras_multipliers"] == "1"
    assert session.submitted["activated_loras"] == [
        "https://huggingface.co/DeepBeepMeep/Qwen_image/resolve/main/loras_accelerators/Qwen-Image-Edit-Lightning-8steps-V1.0-bf16.safetensors"
    ]
    assert backend.loaded_model == "qwen_image_edit_plus_20B_lightning_8"


def test_lightning_variant_availability_requires_base_model_and_lora(tmp_path: Path):
    class FakeSession:
        def list_model_availability(self):
            return [{"model_type": "qwen_image_edit_plus_20B", "available": True}]

    api_file = tmp_path / "shared" / "api.py"
    api_file.parent.mkdir(parents=True)
    api_file.touch()
    backend = WanGPBackend(tmp_path, tmp_path / "outputs", [])
    backend.session = FakeSession()
    assert backend.availability()["qwen_image_edit_plus_20B_lightning_8"] is False

    lora = tmp_path / "loras" / "qwen" / "Qwen-Image-Edit-Lightning-8steps-V1.0-bf16.safetensors"
    lora.parent.mkdir(parents=True)
    lora.touch()
    assert backend.availability()["qwen_image_edit_plus_20B_lightning_8"] is True


def test_h3_turbo_variants_use_base_model_and_lock_turbo_settings(tmp_path: Path):
    class FakeResult:
        success = True
        generated_files = []
        errors = []

    class FakeJob:
        def result(self):
            return FakeResult()

    class FakeSession:
        submitted = None

        def get_default_settings(self, model):
            assert model == "minimax_h3_fl2va_pruned"
            return {"num_inference_steps": 20, "guidance_scale": 1, "flow_shift": 12, "sample_solver": "res_multistep"}

        def submit_task(self, settings, callbacks=None):
            self.submitted = settings
            return FakeJob()

    expected = {
        "minimax_h3_fl2va_pruned_turbo_8": (8, 12, "minimax_h3_light2xv_fl2v_turbo_8step_alpha8_v1.0_bf16.safetensors"),
        "minimax_h3_fl2va_pruned_turbo_4": (4, 6, "minimax_h3_light2xv_fl2v_turbo_4step_alpha128_v1.0_768p_bf16.safetensors"),
    }
    for model_id, (steps, flow_shift, lora) in expected.items():
        backend = WanGPBackend(tmp_path, tmp_path / "outputs", [])
        session = FakeSession()
        backend.session = session
        job = {
            "model": model_id,
            "task": "video.generate",
            "prompt": "a calm scene",
            "parameters": {"num_inference_steps": 50, "guidance_scale": 7, "flow_shift": 1, "resolution": "512x288", "video_length": 25},
        }

        backend._execute_sync_locked(job, {}, lambda *_args: None)

        assert session.submitted["model_type"] == "minimax_h3_fl2va_pruned"
        assert session.submitted["num_inference_steps"] == steps
        assert session.submitted["guidance_scale"] == 1
        assert session.submitted["flow_shift"] == flow_shift
        assert session.submitted["sample_solver"] == "euler"
        assert session.submitted["loras_multipliers"] == "1.0"
        assert session.submitted["activated_loras"] == ["https://huggingface.co/DeepBeepMeep/MiniMax-H3/resolve/main/loras/" + lora]
        assert session.submitted["video_length"] == 25
        assert backend.loaded_model == model_id


def test_h3_turbo_availability_requires_base_model_and_lora(tmp_path: Path):
    class FakeSession:
        def list_model_availability(self):
            return [{"model_type": "minimax_h3_fl2va_pruned", "available": True}]

    api_file = tmp_path / "shared" / "api.py"
    api_file.parent.mkdir(parents=True)
    api_file.touch()
    backend = WanGPBackend(tmp_path, tmp_path / "outputs", [])
    backend.session = FakeSession()
    assert backend.availability()["minimax_h3_fl2va_pruned_turbo_8"] is False
    assert backend.availability()["minimax_h3_fl2va_pruned_turbo_4"] is False

    lora = tmp_path / "loras" / "minimax_h3" / "minimax_h3_light2xv_fl2v_turbo_8step_alpha8_v1.0_bf16.safetensors"
    lora.parent.mkdir(parents=True)
    lora.touch()
    availability = backend.availability()
    assert availability["minimax_h3_fl2va_pruned_turbo_8"] is True
    assert availability["minimax_h3_fl2va_pruned_turbo_4"] is False
