QWEN_EDIT_LIGHTNING_8_ID = "qwen_image_edit_plus_20B_lightning_8"
QWEN_EDIT_LIGHTNING_8_LORA = "Qwen-Image-Edit-Lightning-8steps-V1.0-bf16.safetensors"

H3_FL2VA_BASE = "minimax_h3_fl2va_pruned"
H3_LORA_REPO = "https://huggingface.co/DeepBeepMeep/MiniMax-H3/resolve/main/loras/"
H3_TURBO_8_ID = "minimax_h3_fl2va_pruned_turbo_8"
H3_TURBO_8_LORA = "minimax_h3_light2xv_fl2v_turbo_8step_alpha8_v1.0_bf16.safetensors"
H3_TURBO_4_ID = "minimax_h3_fl2va_pruned_turbo_4"
H3_TURBO_4_LORA = "minimax_h3_light2xv_fl2v_turbo_4step_alpha128_v1.0_768p_bf16.safetensors"


def _h3_turbo_variant(lora: str, steps: int, flow_shift: float) -> dict:
    # Mirrors WanGP's bundled "Turbo Lightx2v FL2V" profiles for MiniMax H3.
    return {
        "base_model": H3_FL2VA_BASE,
        "required_files": (f"loras/minimax_h3/{lora}",),
        "overrides": {
            "activated_loras": [H3_LORA_REPO + lora],
            "loras_multipliers": "1.0",
            "num_inference_steps": steps,
            "guidance_scale": 1,
            "sample_solver": "euler",
            "flow_shift": flow_shift,
        },
    }


MODEL_VARIANTS = {
    QWEN_EDIT_LIGHTNING_8_ID: {
        "base_model": "qwen_image_edit_plus_20B",
        "required_files": (f"loras/qwen/{QWEN_EDIT_LIGHTNING_8_LORA}",),
        "overrides": {
            "activated_loras": [
                "https://huggingface.co/DeepBeepMeep/Qwen_image/resolve/main/loras_accelerators/"
                + QWEN_EDIT_LIGHTNING_8_LORA
            ],
            "loras_multipliers": "1",
            "num_inference_steps": 8,
            "guidance_scale": 1,
            "sample_solver": "default",
        },
    },
    H3_TURBO_8_ID: _h3_turbo_variant(H3_TURBO_8_LORA, steps=8, flow_shift=12),
    H3_TURBO_4_ID: _h3_turbo_variant(H3_TURBO_4_LORA, steps=4, flow_shift=6),
}


MODELS = [
    ("ti2v_2_2", "Wan 2.2 TI2V 5B", "Apache 2.0", ["video.generate", "video.edit"]),
    ("ti2v_2_2_fastwan", "Wan 2.2 TI2V 5B FastWan", "Apache 2.0", ["video.generate", "video.edit"]),
    ("ltx2_25_22B_distilled", "LTX-2.5 Distilled 22B", "LTX Community", ["video.generate", "video.edit", "image.generate", "image.edit"]),
    ("minimax_h3_fl2va_pruned", "MiniMax H3 FL2VA Pruned 20B", "H3 Community", ["video.generate", "video.edit"]),
    (H3_TURBO_8_ID, "MiniMax H3 FL2VA Turbo 8", "H3 Community", ["video.generate", "video.edit"]),
    (H3_TURBO_4_ID, "MiniMax H3 FL2VA Turbo 4", "H3 Community", ["video.generate", "video.edit"]),
    ("minimax_h3_ref2va_pruned", "MiniMax H3 Ref2VA Pruned 20B", "H3 Community", ["video.generate", "video.edit"]),
    ("vace_14B", "Wan VACE 14B", "Apache 2.0", ["video.generate", "video.edit", "image.generate", "image.edit"]),
    ("animate2", "Wan 2.2 Animate 2 14B", "Apache 2.0", ["character.animate"]),
    ("z_image", "Z-Image Turbo 6B", "Apache 2.0", ["image.generate"]),
    ("qwen_image_20B", "Qwen Image 20B", "Apache 2.0", ["image.generate", "image.edit"]),
    ("qwen_image_edit_plus_20B", "Qwen Image Edit Plus", "Apache 2.0", ["image.edit"]),
    (QWEN_EDIT_LIGHTNING_8_ID, "Qwen Image Edit Plus Lightning 8", "Apache 2.0", ["image.edit"]),
    ("qwen_image_edit_plus_20B_nunchaku_r128_int4", "Qwen Image Edit Plus Fast INT4", "Apache 2.0", ["image.edit"]),
    ("qwen3_tts_base", "Qwen3-TTS Base 1.7B", "Apache 2.0", ["speech.clone"]),
    ("qwen3_tts_voicedesign", "Qwen3-TTS Voice Design", "Apache 2.0", ["speech.design"]),
    ("seedvc", "SeedVC", "Verify checkpoint", ["audio.convert"]),
    ("stable_audio3_small_sfx", "Stable Audio 3 Small SFX", "Stability Community", ["sound.generate", "audio.edit"]),
    ("ace_step_v1_5", "ACE-Step 1.5 Turbo", "MIT", ["music.generate", "music.edit"]),
]

TASKS = {model_id: set(tasks) for model_id, _, _, tasks in MODELS}


def public_catalog(availability: dict[str, bool] | None = None) -> list[dict]:
    availability = availability or {}
    return [
        {"id": item[0], "name": item[1], "license": item[2], "tasks": item[3], "installed": availability.get(item[0], False)}
        for item in MODELS
    ]
