"""Download and run one minimal WanGP model smoke test on this machine."""
import json
import os
import sys
import time
import traceback
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
ROOT = (PROJECT / ".runtime" / "Wan2GP").resolve()
INPUTS = Path("N:/local-via-data/smoke-inputs")
OUTPUTS = Path("N:/local-via-data/smoke-outputs")
REPORTS = Path("N:/local-via-data/smoke-reports")
OUTPUTS.mkdir(parents=True, exist_ok=True)
REPORTS.mkdir(parents=True, exist_ok=True)
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from shared.api import init


def base(model: str, **changes):
    return {"model_type": model, "prompt": "A calm cinematic scene, high quality", **changes}


CONFIGS = {
    "z_image": base("z_image", resolution="512x512", num_inference_steps=2, guidance_scale=0, batch_size=1),
    "ti2v_2_2": base("ti2v_2_2", resolution="512x288", video_length=9, num_inference_steps=2, guidance_scale=1, sample_solver="unipc", image_prompt_type=""),
    "ti2v_2_2_fastwan": base("ti2v_2_2_fastwan", resolution="512x288", video_length=9, num_inference_steps=3, guidance_scale=1, sample_solver="unipc", flow_shift=3, image_prompt_type=""),
    "ltx2_25_22B_distilled": base("ltx2_25_22B_distilled", resolution="512x288", video_length=9, num_inference_steps=2, image_prompt_type="", video_prompt_type="", audio_prompt_type=""),
    "minimax_h3_fl2va_pruned": base("minimax_h3_fl2va_pruned", resolution="512x288", video_length=9, num_inference_steps=2, guidance_scale=1),
    "minimax_h3_fl2va_pruned_turbo_8": base("minimax_h3_fl2va_pruned", resolution="512x288", video_length=9, num_inference_steps=8, guidance_scale=1, sample_solver="euler", flow_shift=12, activated_loras=["https://huggingface.co/DeepBeepMeep/MiniMax-H3/resolve/main/loras/minimax_h3_light2xv_fl2v_turbo_8step_alpha8_v1.0_bf16.safetensors"], loras_multipliers="1.0"),
    "minimax_h3_fl2va_pruned_turbo_4": base("minimax_h3_fl2va_pruned", resolution="512x288", video_length=9, num_inference_steps=4, guidance_scale=1, sample_solver="euler", flow_shift=6, activated_loras=["https://huggingface.co/DeepBeepMeep/MiniMax-H3/resolve/main/loras/minimax_h3_light2xv_fl2v_turbo_4step_alpha128_v1.0_768p_bf16.safetensors"], loras_multipliers="1.0"),
    "minimax_h3_ref2va_pruned": base("minimax_h3_ref2va_pruned", resolution="512x288", video_length=9, num_inference_steps=2, guidance_scale=1, image_refs=[str(INPUTS / "reference.jpg")], image_prompt_type="", video_prompt_type="KI"),
    "vace_14B": base("vace_14B", resolution="512x288", video_length=9, num_inference_steps=2, guidance_scale=1, video_prompt_type=""),
    "animate2": base("animate2", resolution="512x512", video_length=17, num_inference_steps=2, guidance_scale=1, image_refs=[str(INPUTS / "reference.jpg")], video_guide=str(INPUTS / "reference.mp4"), image_prompt_type="", video_prompt_type="UVI"),
    "qwen_image_20B": base("qwen_image_20B", resolution="512x512", num_inference_steps=2, guidance_scale=1, sample_solver="default"),
    "qwen_image_edit_plus_20B": base("qwen_image_edit_plus_20B", prompt="Keep the composition and make the sky blue", resolution="512x512", num_inference_steps=2, guidance_scale=1, image_refs=[str(INPUTS / "reference.jpg")], video_prompt_type="KI", model_mode=0, denoising_strength=1),
    "qwen_image_edit_plus_20B_lightning_8": base("qwen_image_edit_plus_20B", prompt="Keep the composition and make the sky blue", resolution="512x512", num_inference_steps=8, guidance_scale=1, sample_solver="default", activated_loras=["https://huggingface.co/DeepBeepMeep/Qwen_image/resolve/main/loras_accelerators/Qwen-Image-Edit-Lightning-8steps-V1.0-bf16.safetensors"], loras_multipliers="1", image_refs=[str(INPUTS / "reference.jpg")], video_prompt_type="KI", model_mode=0, denoising_strength=1),
    "qwen_image_edit_plus_20B_nunchaku_r128_int4": base("qwen_image_edit_plus_20B_nunchaku_r128_int4", prompt="Keep the composition and make the sky blue", resolution="512x512", num_inference_steps=4, guidance_scale=1, sample_solver="default", image_refs=[str(INPUTS / "reference.jpg")], video_prompt_type="KI", model_mode=0, denoising_strength=1),
    "qwen3_tts_base": base("qwen3_tts_base", prompt="Hola, esta es una prueba de voz local.", duration_seconds=2, audio_guide=str(INPUTS / "voice.wav"), audio_prompt_type="A", model_mode="spanish"),
    "qwen3_tts_voicedesign": base("qwen3_tts_voicedesign", prompt="Una voz argentina cálida y serena dice: Hola, esta es una prueba local.", duration_seconds=2, model_mode="spanish"),
    "stable_audio3_small_sfx": base("stable_audio3_small_sfx", prompt="A short soft rain ambience", duration_seconds=2, num_inference_steps=2, guidance_scale=1, sample_solver="pingpong", audio_prompt_type=""),
    "ace_step_v1_5": base("ace_step_v1_5", prompt="Instrumental ambient music, gentle piano, no vocals", duration_seconds=10, num_inference_steps=2, guidance_scale=1, audio_prompt_type=""),
}


def write_report(model: str, payload: dict):
    path = REPORTS / f"{model}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {*CONFIGS, "seedvc"}:
        raise SystemExit(f"Uso: {Path(__file__).name} <modelo>; opciones: {', '.join(sorted([*CONFIGS, 'seedvc']))}")
    model = sys.argv[1]
    started = time.time()
    report = {"model": model, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "success": False}
    try:
        session = init(root=ROOT, output_dir=OUTPUTS, cli_args=["--attention", "sdpa", "--profile", "4"], console_output=True)
        if model == "seedvc":
            job = session.submit_audio_postprocessing(str(INPUTS / "voice.wav"), postprocess_audio="seedvc_one_speaker", replace_voice_sample=str(INPUTS / "voice2.wav"))
        else:
            settings = session.get_default_settings(model) or {}
            settings.update(CONFIGS[model])
            job = session.submit_task(settings)
        result = job.result()
        report.update({
            "success": bool(result.success),
            "generated_files": [str(path) for path in result.generated_files],
            "errors": [getattr(error, "message", str(error)) for error in result.errors],
        })
        if not result.success:
            raise RuntimeError("; ".join(report["errors"]) or "generation failed")
    except Exception as error:
        report.update({"error": str(error), "traceback": traceback.format_exc()})
    finally:
        report["duration_seconds"] = round(time.time() - started, 2)
        path = write_report(model, report)
        print(f"SMOKE_REPORT={path}", flush=True)
        print(json.dumps(report, ensure_ascii=False, default=str), flush=True)
    raise SystemExit(0 if report["success"] else 1)


if __name__ == "__main__":
    main()
