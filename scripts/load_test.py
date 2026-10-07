"""Load test: many students against a simulated classroom (hub + mock workers), through the real HTTP API.

Checks that every job finishes exactly once, that no computer ever runs two jobs at the same time,
that jobs start in FIFO order (within the warm-model affinity window) and reports queue waits.
Usage: .venv/Scripts/python.exe scripts/load_test.py --students 40 --jobs 3 --workers 8
"""
import argparse
import concurrent.futures
import json
import sqlite3
import statistics
import subprocess
import sys
import time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "alumno-dev-password"


def student_run(base: str, index: int, jobs: int) -> list[str]:
    client = httpx.Client(base_url=base, headers={"X-LocalVia": "1"}, timeout=30)
    assert client.post("/api/auth/login", json={"username": f"alumno{index}", "password": PASSWORD}).status_code == 200
    done = []
    for number in range(jobs):
        while True:
            response = client.post("/api/jobs", json={"model": "z_image", "task": "image.generate", "prompt": f"alumno{index} pedido {number}", "parameters": {}})
            if response.status_code == 200: break
            assert response.status_code == 429, response.text  # still has a job in progress
            time.sleep(0.5)
        job_id = response.json()["id"]
        while True:
            state = client.get("/api/state").json()
            job = next(item for item in state["jobs"] if item["id"] == job_id)
            # A student must only ever see their own jobs.
            assert all(item["prompt"].startswith(f"alumno{index} ") for item in state["jobs"])
            if job["status"] in ("succeeded", "failed", "cancelled"): break
            time.sleep(0.5)
        assert job["status"] == "succeeded", job
        assert client.get(job["artifacts"][0]["url"]).status_code == 200
        done.append(job_id)
    return done


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--students", type=int, default=40)
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--mock-seconds", type=float, default=3.0)
    parser.add_argument("--port", type=int, default=8097)
    args = parser.parse_args()
    data_dir = "data/load-classroom"
    classroom = subprocess.Popen([sys.executable, "scripts/dev_classroom.py", "--workers", str(args.workers), "--students", str(args.students),
                                  "--port", str(args.port), "--mock-seconds", str(args.mock_seconds), "--reset", "--data-dir", data_dir],
                                 cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://localhost:{args.port}"
    try:
        for _ in range(60):
            try:
                if httpx.get(f"{base}/healthz").status_code == 200: break
            except httpx.HTTPError: time.sleep(0.5)
        time.sleep(3)
        started = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.students) as pool:
            results = list(pool.map(lambda index: student_run(base, index, args.jobs), range(1, args.students + 1)))
        elapsed = time.time() - started
    finally:
        if sys.platform == "win32": subprocess.run(["taskkill", "/F", "/T", "/PID", str(classroom.pid)], capture_output=True)
        else: classroom.terminate()

    db = sqlite3.connect(ROOT / data_dir / "hub" / "hub.db")
    rows = db.execute("SELECT id, worker_id, created_at, claimed_at, finished_at, attempts, status FROM jobs ORDER BY created_at").fetchall()
    total = args.students * args.jobs
    assert len(rows) == total and sum(len(item) for item in results) == total
    assert all(row[6] == "succeeded" and row[5] == 1 for row in rows), "every job succeeds on its first and only dispatch"
    by_worker: dict[str, list] = {}
    for row in rows: by_worker.setdefault(row[1], []).append((row[3], row[4]))
    for worker, spans in by_worker.items():
        spans.sort()
        assert all(spans[i][1] <= spans[i + 1][0] + 1e-6 for i in range(len(spans) - 1)), f"{worker} ran two jobs at once"
    claimed_order = [row[0] for row in sorted(rows, key=lambda row: row[3])]
    created_order = [row[0] for row in rows]
    inversions = sum(1 for index, job in enumerate(claimed_order) if created_order.index(job) < index - args.workers)
    waits = [row[3] - row[2] for row in rows]
    report = {
        "students": args.students, "jobs_per_student": args.jobs, "workers": args.workers, "mock_seconds_per_job": args.mock_seconds,
        "jobs_total": total, "elapsed_seconds": round(elapsed, 1),
        "throughput_jobs_per_minute": round(total / elapsed * 60, 1),
        "ideal_jobs_per_minute": round(args.workers * 60 / args.mock_seconds, 1),
        "jobs_per_worker": {worker: len(spans) for worker, spans in sorted(by_worker.items())},
        "queue_wait_seconds": {"median": round(statistics.median(waits), 1), "max": round(max(waits), 1)},
        "fifo_violations_beyond_worker_count": inversions,
        "double_dispatch": 0, "overlapping_jobs_per_worker": 0, "failed_jobs": 0,
    }
    assert inversions == 0
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
