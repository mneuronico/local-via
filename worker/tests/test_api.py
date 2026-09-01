import os
import tempfile
from pathlib import Path

temp = Path(tempfile.mkdtemp(prefix="local-via-tests-"))
os.environ["LOCAL_VIA_DATA_DIR"] = str(temp)
os.environ["LOCAL_VIA_BACKEND"] = "mock"

from fastapi.testclient import TestClient
from worker.app.main import app
from worker.app.config import settings

HEADERS = {"Authorization": f"Bearer {settings.token}"}


def test_health_and_auth():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"ok": True}
        assert client.get("/v1/status").status_code == 401
        assert client.get("/v1/status", headers=HEADERS).status_code == 200


def test_local_browser_does_not_need_a_token():
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
        response = client.get("/v1/status", headers={"Origin": "http://localhost:3000"})
        assert response.status_code == 200


def test_job_finishes_and_artifact_is_signed():
    with TestClient(app) as client:
        created = client.post("/v1/jobs", headers=HEADERS, json={"model": "z_image", "task": "image.generate", "prompt": "A small observatory"})
        assert created.status_code == 200
        job_id = created.json()["id"]
        import time
        for _ in range(30):
            job = client.get(f"/v1/jobs/{job_id}", headers=HEADERS).json()
            if job["status"] == "succeeded": break
            time.sleep(.1)
        assert job["status"] == "succeeded", job
        assert len(job["artifacts"]) == 1
        repeated = client.get(f"/v1/jobs/{job_id}", headers=HEADERS).json()
        assert repeated["artifacts"][0]["url"] == job["artifacts"][0]["url"]
        response = client.get(job["artifacts"][0]["url"])
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/svg+xml")
