"""End-to-end: a real Agent (mock backend) pulls work from a real hub app over HTTP."""
import asyncio
import time
import httpx
from hub.app.config import HubSettings
from hub.app.main import create_app
from hub.app.security import hash_password, token_hash
from worker.app.agent import Agent
from worker.app.config import WorkerSettings

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def setup(tmp_path, mock_seconds: float):
    app = create_app(HubSettings(_env_file=None, data_dir=tmp_path / "hub", ui_dir=tmp_path / "none", claim_wait_seconds=1))
    state = app.state.hub
    state.db.execute("INSERT INTO users (id, username, display_name, password_hash, role, created_at) VALUES ('u1','ana','Ana',?, 'student', ?)",
                     (hash_password("password-123"), time.time()))
    state.db.execute("INSERT INTO workers (id, token_hash, created_at) VALUES ('pc-01', ?, ?)", (token_hash("secret-token"), time.time()))
    transport = httpx.ASGITransport(app=app, client=("10.0.0.21", 40000))
    worker_settings = WorkerSettings(_env_file=None, hub_url="http://hub", token="secret-token", data_dir=tmp_path / "worker",
                                     mock_seconds=mock_seconds, heartbeat_seconds=0.1, max_gpu_temp_c=0)
    agent = Agent(worker_settings, transport=transport)
    student = httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("10.0.0.50", 50000)), base_url="http://hub", headers={"X-LocalVia": "1"})
    return app, agent, student, worker_settings


async def wait_for(student: httpx.AsyncClient, predicate, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = (await student.get("/api/state")).json()
        if predicate(state): return state
        await asyncio.sleep(0.05)
    raise AssertionError(f"timeout: {state}")


def test_agent_runs_job_with_inputs_and_cleans_up(tmp_path):
    async def scenario():
        app, agent, student, worker_settings = setup(tmp_path, 0.2)
        runner = asyncio.create_task(agent.run())
        try:
            assert (await student.post("/api/auth/login", json={"username": "ana", "password": "password-123"})).status_code == 200
            await wait_for(student, lambda state: state["room"]["workers_online"] == 1)
            created = (await student.post("/api/uploads", json={"name": "foto.png", "size": len(PNG), "input_key": "image_primary"})).json()
            await student.put(f"/api/uploads/{created['id']}/chunks/0", content=PNG)
            assert (await student.post(f"/api/uploads/{created['id']}/complete")).status_code == 200
            job = (await student.post("/api/jobs", json={"model": "qwen_image_edit_plus_20B", "task": "image.edit", "prompt": "lluvia",
                                                          "inputs": {"image_primary": created["id"]}, "parameters": {}})).json()
            state = await wait_for(student, lambda s: s["jobs"][0]["status"] in ("succeeded", "failed"))
            done = state["jobs"][0]
            assert done["id"] == job["id"] and done["status"] == "succeeded", done
            artifact = done["artifacts"][0]
            assert artifact["media_type"] == "image/png"
            body = (await student.get(artifact["url"])).content
            assert body.startswith(b"\x89PNG")
            # Nothing from the student stays on the lab PC.
            assert not any((worker_settings.data_dir / "jobs").glob("*/*"))
            worker = app.state.hub.db.one("SELECT * FROM workers WHERE id='pc-01'")
            assert worker["ip"] == "10.0.0.21" and worker["current_job_id"] is None
        finally:
            agent.stopping.set(); await asyncio.wait_for(runner, 5); await student.aclose()
    asyncio.run(scenario())


def test_agent_honours_cancellation(tmp_path):
    async def scenario():
        _, agent, student, _ = setup(tmp_path, 3.0)
        runner = asyncio.create_task(agent.run())
        try:
            await student.post("/api/auth/login", json={"username": "ana", "password": "password-123"})
            await wait_for(student, lambda state: state["room"]["workers_online"] == 1)
            job = (await student.post("/api/jobs", json={"model": "z_image", "task": "image.generate", "prompt": "x", "parameters": {}})).json()
            await wait_for(student, lambda s: s["jobs"][0]["status"] == "running")
            await student.post(f"/api/jobs/{job['id']}/cancel")
            state = await wait_for(student, lambda s: s["jobs"][0]["status"] == "cancelled", timeout=5)
            assert state["jobs"][0]["artifacts"] == []
        finally:
            agent.stopping.set(); await asyncio.wait_for(runner, 5); await student.aclose()
    asyncio.run(scenario())


def test_agent_reports_backend_failures(tmp_path):
    class Broken:
        name, loaded_model = "broken", None
        def availability(self): return {"z_image": True}
        async def execute(self, *_): raise RuntimeError("CUDA out of memory")
        def cancel(self): pass

    async def scenario():
        _, agent, student, _ = setup(tmp_path, 0.1)
        agent.backend = Broken()
        runner = asyncio.create_task(agent.run())
        try:
            await student.post("/api/auth/login", json={"username": "ana", "password": "password-123"})
            await wait_for(student, lambda state: state["room"]["workers_online"] == 1)
            await student.post("/api/jobs", json={"model": "z_image", "task": "image.generate", "prompt": "x", "parameters": {}})
            state = await wait_for(student, lambda s: s["jobs"][0]["status"] == "failed")
            assert "CUDA out of memory" in state["jobs"][0]["error"]
        finally:
            agent.stopping.set(); await asyncio.wait_for(runner, 5); await student.aclose()
    asyncio.run(scenario())
