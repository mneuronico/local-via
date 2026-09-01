# Model compatibility audit — RTX 2060 12 GB

Audited against the checked-out WanGP `main` source and its built-in default definitions on 2026-08-13.

| Local Via id | WanGP definition | 12 GB strategy | Status |
|---|---|---|---|
| `ti2v_2_2` | Wan 2.2 TI2V 5B | INT8/offload, 480p first | **Inference passed** |
| `ltx2_25_22B_distilled` | LTX-2.5 Distilled 22B | INT8 ConvRot, 8 steps, 432/480p first | **Inference passed on this RTX 2060** |
| `minimax_h3_fl2va_pruned` | H3 FL2VA Pruned 20B | INT8 ConvRot, short 480p clips | **Inference passed** |
| `minimax_h3_ref2va_pruned` | H3 Ref2VA Pruned 20B | INT8 ConvRot, one reference first | **Inference passed on this RTX 2060** |
| `minimax_h3_fl2va_pruned_turbo_8` | H3 FL2VA Pruned 20B + Lightx2v Turbo 8-step LoRA | Same INT8 ConvRot checkpoint, LoRA 1.38 GB, 8 steps, guidance 1, flow shift 12 | **Inference passed on this RTX 2060** (2026-09-01, 512x288, 49 frames) |
| `minimax_h3_fl2va_pruned_turbo_4` | H3 FL2VA Pruned 20B + Lightx2v Turbo 4-step 768p LoRA | Same INT8 checkpoint, 4 steps, guidance 1, flow shift 6 | Catalogued, **not yet run on this machine** |
| `vace_14B` | Wan VACE 14B | INT8/offload, 480p | **Inference passed** |
| `animate2` | Wan 2.2 Animate 2 14B | INT8 ConvRot, short driving clip | **Inference passed with image + driving video** |
| `z_image` | Z-Image Turbo 6B | INT8, 8 steps | **Inference passed on this RTX 2060** |
| `qwen_image_20B` | Qwen Image 20B | INT8/offload | **Inference passed** |
| `qwen_image_edit_plus_20B` | Qwen Image Edit Plus 20B | INT8, 720–1024 square | **Inference passed with image reference** |
| `qwen3_tts_base` | Qwen3 TTS Base 1.7B | INT8 | **Inference passed with voice reference** |
| `qwen3_tts_voicedesign` | Qwen3 TTS Voice Design 1.7B | INT8 | **Inference passed** |
| `seedvc` | WanGP audio postprocessor | One-speaker postprocess | **Conversion passed with source + target voice** |
| `stable_audio3_small_sfx` | Stable Audio 3 Small SFX | BF16, 8 steps | **Inference passed** |
| `ace_step_v1_5` | ACE-Step 1.5 Turbo 2B | INT8/BF16, 8 steps | **Inference passed** |

Both Turbo rows reuse the FL2VA pruned checkpoint already on disk and only add a LoRA that WanGP downloads on first use; they mirror WanGP's bundled "Turbo Lightx2v FL2V" profiles. Turbo 4 was deliberately left unverified after the 2026-09-01 crash (see [MODEL_BENCHMARKS.md](MODEL_BENCHMARKS.md)).

Every catalog row above except Turbo 4 produced a real file under `N:\local-via-data\smoke-outputs`; its JSON report is under `N:\local-via-data\smoke-reports`. The checkpoint store currently occupies about 238 GB on `N:`. The UI reports `installed` from WanGP's own availability scan when the real backend is enabled.

WanGP's current Windows guidance for RTX 20xx calls for Python 3.11, PyTorch 2.10/CUDA 13, Triton Windows, Sage Attention 1, Flash Attention, Nunchaku and GGUF kernels. This computer has a compatible NVIDIA driver but `nvcc`/the CUDA toolkit was not detected during the audit.
