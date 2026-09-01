import json
import os
import sys
from pathlib import Path

ROOT = (Path(__file__).resolve().parents[1] / ".runtime" / "Wan2GP").resolve()
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from shared.api import init

TARGETS = {
    "ti2v_2_2", "ti2v_2_2_fastwan", "ltx2_25_22B_distilled", "minimax_h3_fl2va_pruned",
    "minimax_h3_ref2va_pruned", "vace_14B", "animate2", "z_image",
    "qwen_image_20B", "qwen_image_edit_plus_20B", "qwen_image_edit_plus_20B_nunchaku_r128_int4", "qwen3_tts_base",
    "qwen3_tts_voicedesign", "stable_audio3_small_sfx", "ace_step_v1_5",
}

session = init(root=ROOT, cli_args=["--attention", "sdpa", "--profile", "4"], console_output=False)
metadata = {row["model_type"]: row for row in session.list_model_metadata() if row.get("model_type") in TARGETS}
availability = {row["model_type"]: row for row in session.list_model_availability() if row.get("model_type") in TARGETS}
print(json.dumps({"root": str(ROOT), "found": sorted(metadata), "metadata": metadata, "availability": availability}, indent=2, default=str))
