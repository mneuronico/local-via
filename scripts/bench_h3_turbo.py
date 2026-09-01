"""Measure MiniMax H3 FL2VA base vs Turbo variants through the running local worker.

Usage: python scripts/bench_h3_turbo.py [--resolution 512x288] [--frames 49] [--repeat 2] [--models a,b,c]
Submits text-to-video jobs sequentially to http://127.0.0.1:9000 and reports wall time per job.
"""
import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

WORKER = "http://127.0.0.1:9000"
HEADERS = {"Origin": "http://localhost:3000", "Content-Type": "application/json"}
REPORTS = Path("N:/local-via-data/smoke-reports")
PROMPT = "A calm cinematic shot of a small wooden boat drifting on a misty lake at dawn, soft ripples, distant birds singing"
DEFAULT_MODELS = ["minimax_h3_fl2va_pruned", "minimax_h3_fl2va_pruned_turbo_8", "minimax_h3_fl2va_pruned_turbo_4"]


def request(method: str, path: str, payload: dict | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(WORKER + path, data=data, method=method, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read())


def run_job(model: str, resolution: str, frames: int, seed: int) -> dict:
    parameters = {"resolution": resolution, "video_length": frames, "seed": seed, "num_inference_steps": 20, "guidance_scale": 1, "sample_solver": "euler", "flow_shift": 12}
    started = time.time()
    job = request("POST", "/v1/jobs", {"model": model, "task": "video.generate", "prompt": PROMPT, "parameters": parameters})
    phases: list[tuple[float, str, int]] = []
    last = None
    while job["status"] in {"queued", "running"}:
        time.sleep(5)
        job = request("GET", f"/v1/jobs/{job['id']}")
        marker = (job.get("phase"), job.get("progress"))
        if marker != last:
            phases.append((round(time.time() - started, 1), str(job.get("phase")), int(job.get("progress") or 0)))
            print(f"  [{phases[-1][0]:7.1f}s] {model}: {job.get('phase')} {job.get('progress')}%", flush=True)
            last = marker
    wall = round(time.time() - started, 1)
    created, updated = datetime.fromisoformat(job["created_at"]), datetime.fromisoformat(job["updated_at"])
    return {"model": model, "job_id": job["id"], "status": job["status"], "error": job.get("error"), "wall_seconds": wall,
            "worker_seconds": round((updated - created).total_seconds(), 1), "phases": phases,
            "artifacts": [artifact["name"] for artifact in job.get("artifacts", [])]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resolution", default="512x288")
    parser.add_argument("--frames", type=int, default=49)
    parser.add_argument("--repeat", type=int, default=2)
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--models", default=",".join(DEFAULT_MODELS))
    parser.add_argument("--tag", default="")
    args = parser.parse_args()
    models = [model for model in args.models.split(",") if model]
    report = {"started_at": datetime.now().isoformat(timespec="seconds"), "resolution": args.resolution, "frames": args.frames, "prompt": PROMPT, "runs": []}
    for model in models:
        for index in range(args.repeat):
            label = "cold" if index == 0 else "warm"
            print(f"== {model} ({label}) {args.resolution} x {args.frames} frames", flush=True)
            result = run_job(model, args.resolution, args.frames, args.seed)
            result["label"] = label
            report["runs"].append(result)
            print(f"   -> {result['status']} in {result['wall_seconds']}s (worker {result['worker_seconds']}s) {result['error'] or ''}", flush=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    name = f"bench_h3_turbo_{args.resolution}_{args.frames}f{('_' + args.tag) if args.tag else ''}.json"
    (REPORTS / name).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nREPORT={REPORTS / name}")
    print(f"{'model':42} {'run':5} {'status':10} {'wall s':>8} {'worker s':>9}")
    for run in report["runs"]:
        print(f"{run['model']:42} {run['label']:5} {run['status']:10} {run['wall_seconds']:8.1f} {run['worker_seconds']:9.1f}")
    return 0 if all(run["status"] == "succeeded" for run in report["runs"]) else 1


if __name__ == "__main__":
    sys.exit(main())
