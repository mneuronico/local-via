"""Simulated classroom for development, end-to-end tests and the bandwidth measurement.

Starts the hub plus N mock workers (no GPU) in a throwaway data directory and seeds test accounts.
Usage (from the repository root):
    .venv/Scripts/python.exe scripts/dev_classroom.py --workers 8 --port 8090 --reset

Test accounts created here are development fixtures only:
    admin   / admin-dev-password      (administration)
    alumno1..alumno30 / alumno-dev-password
"""
import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN = ("admin", "admin-dev-password")
STUDENT_PASSWORD = "alumno-dev-password"
CLASS_CODE = "DEMO-2026"


def seed(data_dir: Path, workers: int, students: int) -> dict[str, str]:
    sys.path.insert(0, str(ROOT))
    from hub.app.db import Database
    from hub.app.security import hash_password, token_hash
    db = Database(data_dir / "hub.db")
    now = time.time()
    if not db.one("SELECT id FROM users WHERE username=?", (ADMIN[0],)):
        db.execute("INSERT INTO users (id, username, display_name, password_hash, role, created_at) VALUES (?,?,?,?,?,?)",
                   (uuid.uuid4().hex, ADMIN[0], "Administración", hash_password(ADMIN[1]), "admin", now))
    if not db.one("SELECT id FROM classes WHERE code=?", (CLASS_CODE,)):
        db.execute("INSERT INTO classes (id, name, code, created_at) VALUES (?,?,?,?)", (uuid.uuid4().hex, "Clase de prueba", CLASS_CODE, now))
    student_hash = hash_password(STUDENT_PASSWORD)
    for index in range(1, students + 1):
        name = f"alumno{index}"
        if not db.one("SELECT id FROM users WHERE username=?", (name,)):
            db.execute("INSERT INTO users (id, username, display_name, password_hash, role, created_at) VALUES (?,?,?,?,?,?)",
                       (uuid.uuid4().hex, name, f"Alumno {index}", student_hash, "student", now))
    tokens = {}
    for index in range(1, workers + 1):
        name, token = f"aula-pc-{index:02d}", f"dev-worker-token-{index:02d}"
        db.execute("INSERT INTO workers (id, token_hash, created_at) VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET token_hash=excluded.token_hash, disabled=0",
                   (name, token_hash(token), now))
        tokens[name] = token
    db.close()
    return tokens


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--students", type=int, default=30)
    parser.add_argument("--mock-seconds", type=float, default=20.0)
    parser.add_argument("--samples-dir", default="")
    parser.add_argument("--data-dir", default="data/dev-classroom")
    parser.add_argument("--tls", action="store_true", help="serve HTTPS with a throwaway self-signed certificate")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--worker-hub-url", default="", help="URL the workers use (e.g. a byte-counting proxy)")
    args = parser.parse_args()

    data_dir = (ROOT / args.data_dir).resolve()
    if args.reset and data_dir.exists(): shutil.rmtree(data_dir)
    hub_dir = data_dir / "hub"; hub_dir.mkdir(parents=True, exist_ok=True)
    tokens = seed(hub_dir, args.workers, args.students)

    env = {**os.environ, "LOCALVIA_HUB_DATA_DIR": str(hub_dir), "LOCALVIA_HUB_UI_DIR": str(ROOT / "out"),
           "LOCALVIA_HUB_HOST": "127.0.0.1", "LOCALVIA_HUB_PORT": str(args.port), "LOCALVIA_HUB_MODE": "lan",
           "LOCALVIA_HUB_RETENTION_DAYS": "14", "LOCALVIA_HUB_LOGIN_MAX_FAILURES": "50"}
    scheme = "http"
    if args.tls:
        cert_dir = data_dir / "certs"
        subprocess.run([sys.executable, "-m", "hub.cli", "make-cert", "--hosts", "localhost", "--out", str(cert_dir)], cwd=ROOT, check=True, env=env, stdout=subprocess.DEVNULL)
        env.update({"LOCALVIA_HUB_TLS_CERT_FILE": str(cert_dir / "hub.crt"), "LOCALVIA_HUB_TLS_KEY_FILE": str(cert_dir / "hub.key")})
        scheme = "https"
    hub_url = f"{scheme}://localhost:{args.port}"
    children = [subprocess.Popen([sys.executable, "-m", "hub"], cwd=ROOT, env=env)]
    time.sleep(1.5)
    for name, token in tokens.items():
        worker_env = {**os.environ, "LOCALVIA_WORKER_HUB_URL": args.worker_hub_url or hub_url, "LOCALVIA_WORKER_TOKEN": token, "LOCALVIA_WORKER_BACKEND": "mock",
                      "LOCALVIA_WORKER_DATA_DIR": str(data_dir / name), "LOCALVIA_WORKER_MOCK_SECONDS": str(args.mock_seconds),
                      "LOCALVIA_WORKER_MAX_GPU_TEMP_C": "0"}
        if args.samples_dir: worker_env["LOCALVIA_WORKER_MOCK_SAMPLES_DIR"] = str(Path(args.samples_dir).resolve())
        if args.tls: worker_env["LOCALVIA_WORKER_CA_FILE"] = str(data_dir / "certs" / "hub.crt")
        children.append(subprocess.Popen([sys.executable, "-m", "worker"], cwd=ROOT, env=worker_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    (data_dir / "classroom.json").write_text(json.dumps({"url": hub_url, "workers": list(tokens), "class_code": CLASS_CODE}), encoding="utf-8")
    print(f"Sala simulada lista en {hub_url} con {args.workers} computadoras (mock, {args.mock_seconds:g} s por pedido)", flush=True)

    def stop(*_):
        for child in children:
            if child.poll() is None: child.terminate()
        for child in children:
            try: child.wait(10)
            except subprocess.TimeoutExpired: child.kill()
        sys.exit(0)
    signal.signal(signal.SIGINT, stop); signal.signal(signal.SIGTERM, stop)
    try:
        while children[0].poll() is None: time.sleep(1)
    finally:
        stop()


if __name__ == "__main__":
    main()
