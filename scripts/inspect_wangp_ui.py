import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / ".runtime" / "Wan2GP"
sys.path.insert(0, str(ROOT))
from shared.api import init  # noqa: E402

TARGETS = sys.argv[1:] or [
    "ti2v_2_2", "ltx2_25_22B_distilled", "minimax_h3_fl2va_pruned",
    "minimax_h3_ref2va_pruned", "vace_14B", "animate2", "z_image",
    "qwen_image_20B", "qwen_image_edit_plus_20B", "qwen3_tts_base",
    "qwen3_tts_voicedesign", "stable_audio3_small_sfx", "ace_step_v1_5",
]

session = init(root=ROOT, cli_args=["--attention", "sdpa", "--profile", "4"], console_output=False)
result = {}
for model_id in TARGETS:
    schema = session.get_model_schema(model_id)
    metadata = schema["metadata"]
    defaults = schema["default_settings"]
    result[model_id] = {
        "name": schema["model_def"].get("name", model_id),
        "inputs": metadata["inputs"],
        "outputs": metadata["outputs"],
        "media_inputs": metadata["media_inputs"],
        "capabilities": metadata["capabilities"],
        "setting_values": metadata["setting_values"],
        "defaults": {key: defaults.get(key) for key in (
            "resolution", "video_length", "duration_seconds", "num_inference_steps",
            "guidance_scale", "guidance2_scale", "guidance3_scale", "audio_guidance_scale",
            "embedded_guidance_scale", "seed", "sample_solver", "flow_shift",
            "temperature", "top_p", "top_k", "batch_size", "repeat_generation",
            "image_prompt_type", "video_prompt_type", "audio_prompt_type", "model_mode",
            "denoising_strength", "masking_strength", "input_video_strength",
            "frames_positions", "speakers_locations", "force_fps", "output_type",
        ) if key in defaults},
    }
print(json.dumps(result, ensure_ascii=False, indent=2))
