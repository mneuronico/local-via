"""Hub-side view of the model catalog. The worker catalog is the single source of model ids and tasks."""
from worker.app.catalog import MODELS, TASKS

MODEL_NAMES = {model_id: name for model_id, name, _, _ in MODELS}

# Parameter keys the studio UI can send. Anything else is rejected before it reaches WanGP.
ALLOWED_PARAMETERS = {
    "audio_prompt_type", "batch_size", "denoising_strength", "duration_seconds", "flow_shift", "force_fps",
    "frames_positions", "guidance_scale", "guide_preprocess", "image_prompt_type", "image_ref_mode",
    "mask_preprocess", "masking_strength", "model_mode", "negative_prompt", "num_inference_steps",
    "prompt_enhancer", "repeat_generation", "resolution", "sample_solver", "seed", "temperature", "top_k",
    "top_p", "video_length", "video_prompt_type",
}

# Input roles accepted by the WanGP adapter, with the media family each one must contain.
INPUT_KINDS = {
    "image_primary": "image", "image_refs": "image", "image_start": "image", "image_end": "image",
    "image_guide": "image", "image_mask": "image",
    "video_source": "video", "video_guide": "video", "video_refs": "video", "video_mask": "video",
    "audio_guide": "audio", "audio_guide2": "audio", "audio_source": "audio", "voice_reference": "audio",
}
MAX_FILES_PER_INPUT = 8

# Conservative classroom defaults; the admin panel can change them at runtime.
DEFAULT_POLICY = {
    "enabled_models": [model_id for model_id, *_ in MODELS],
    "max_pixels": 1280 * 720 + 128 * 1024,  # allows 1280x720, 1280x704 and 1024x1024
    "max_video_frames": 241,
    "max_steps": 50,
    "max_audio_seconds": 120,
    "max_batch_size": 4,
}

# Typical durations (seconds) used for queue estimates until the hub has its own history.
DEFAULT_DURATION = {"image": 120, "video": 900, "audio": 180}


def output_kind(task: str) -> str:
    family = task.split(".", 1)[0]
    if family == "image": return "image"
    if family in ("video", "character"): return "video"
    return "audio"


__all__ = ["MODELS", "TASKS", "MODEL_NAMES", "ALLOWED_PARAMETERS", "INPUT_KINDS", "MAX_FILES_PER_INPUT", "DEFAULT_POLICY", "DEFAULT_DURATION", "output_kind"]
