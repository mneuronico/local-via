import time
from .conftest import API, PNG, add_user, add_worker, login, make_client, upload

JOB = {"model": "z_image", "task": "image.generate", "prompt": "Un faro al atardecer", "parameters": {"resolution": "512x512", "num_inference_steps": 8}}


def worker_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---- authentication and sessions ------------------------------------------------------------

def test_api_requires_login_and_csrf_header(app, hub):
    add_user(hub, "ana")
    with make_client(app) as client:
        assert client.get("/api/state").status_code == 401
        client.headers.pop("X-LocalVia")
        assert client.post("/api/auth/login", json={"username": "ana", "password": "password-123"}).status_code == 403
        assert client.post("/api/auth/login", json={"username": "ana", "password": "password-123"}, headers={**API, "Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_login_sets_httponly_strict_cookie_and_logout_revokes(app, hub):
    add_user(hub, "ana")
    with make_client(app) as client:
        response = client.post("/api/auth/login", json={"username": "ANA", "password": "password-123"})
        assert response.status_code == 200
        cookie = response.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=strict" in cookie
        assert client.get("/api/me").json()["user"]["username"] == "ana"
        assert client.post("/api/auth/logout").status_code == 200
        assert client.get("/api/me").status_code == 401


def test_secure_host_cookie_in_tunnel_mode(tmp_path):
    from hub.app.config import HubSettings
    from hub.app.main import create_app
    app = create_app(HubSettings(_env_file=None, mode="tunnel", data_dir=tmp_path / "t", ui_dir=tmp_path / "x"))
    add_user(app.state.hub, "ana")
    with make_client(app) as client:
        cookie = client.post("/api/auth/login", json={"username": "ana", "password": "password-123"}).headers["set-cookie"]
        assert cookie.startswith("__Host-lv_session=") and "Secure" in cookie


def test_login_is_rate_limited(app, hub):
    add_user(hub, "ana")
    with make_client(app) as client:
        for _ in range(5):
            assert client.post("/api/auth/login", json={"username": "ana", "password": "wrong-password"}).status_code == 401
        assert client.post("/api/auth/login", json={"username": "ana", "password": "password-123"}).status_code == 429


def test_register_with_class_code(app, hub):
    add_user(hub, "profe", role="admin")
    admin = login(app, "profe")
    code = admin.post("/api/admin/classes", json={"name": "Taller 2026", "max_uses": 1}).json()["code"]
    with make_client(app) as client:
        assert client.post("/api/auth/register", json={"class_code": "NOPE-NOPE", "username": "luz", "password": "password-123"}).status_code == 403
        ok = client.post("/api/auth/register", json={"class_code": code.lower(), "username": "luz", "password": "password-123"})
        assert ok.status_code == 200 and ok.json()["user"]["role"] == "student"
        assert client.get("/api/me").status_code == 200
    with make_client(app) as other:
        assert other.post("/api/auth/register", json={"class_code": code, "username": "sol", "password": "password-123"}).status_code == 403


def test_security_headers_present(client):
    response = client.get("/healthz")
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"


# ---- isolation between students -------------------------------------------------------------

def test_students_cannot_see_or_touch_each_other(app, hub):
    add_user(hub, "ana"); add_user(hub, "beto"); token = add_worker(hub, "pc-01")
    ana, beto = login(app, "ana"), login(app, "beto")
    upload_id = upload(ana)
    assert beto.post("/api/jobs", json={**JOB, "model": "qwen_image_edit_plus_20B", "task": "image.edit", "inputs": {"image_primary": upload_id}}).status_code == 422
    job = ana.post("/api/jobs", json=JOB).json()
    assert [item["id"] for item in ana.get("/api/state").json()["jobs"]] == [job["id"]]
    assert beto.get("/api/state").json()["jobs"] == []
    assert beto.post(f"/api/jobs/{job['id']}/cancel").status_code == 404
    with make_client(app) as worker:
        claimed = worker.post("/worker-api/claim", json={"state": {}}, headers=worker_headers(token)).json()
        artifact = worker.put(f"/worker-api/jobs/{claimed['id']}/artifacts", params={"name": "out.png"}, content=PNG, headers=worker_headers(token)).json()
        worker.post(f"/worker-api/jobs/{claimed['id']}/complete", json={"status": "succeeded"}, headers=worker_headers(token))
    assert ana.get(f"/api/files/{artifact['id']}").status_code == 200
    assert beto.get(f"/api/files/{artifact['id']}").status_code == 404
    assert ana.get(f"/api/files/{artifact['id']}").headers["content-security-policy"].endswith("sandbox")


# ---- uploads ----------------------------------------------------------------------------------

def test_upload_rejects_wrong_type_size_and_order(app, hub, settings):
    add_user(hub, "ana"); ana = login(app, "ana")
    created = ana.post("/api/uploads", json={"name": "x.png", "size": 20, "input_key": "image_primary"}).json()
    assert ana.put(f"/api/uploads/{created['id']}/chunks/1", content=b"x").status_code == 409
    assert ana.put(f"/api/uploads/{created['id']}/chunks/0", content=b"x" * 21).status_code == 413
    ana.put(f"/api/uploads/{created['id']}/chunks/0", content=b"<script>alert(1)</script>"[:20])
    assert ana.post(f"/api/uploads/{created['id']}/complete").status_code == 422
    too_big = settings.max_upload_mb * 1024 * 1024 + 1
    assert ana.post("/api/uploads", json={"name": "x.png", "size": too_big, "input_key": "image_primary"}).status_code == 413
    assert ana.post("/api/uploads", json={"name": "x.png", "size": 10, "input_key": "not_a_role"}).status_code == 422
    # A PNG declared for an audio role is rejected after sniffing the content.
    audio = ana.post("/api/uploads", json={"name": "a.wav", "size": len(PNG), "input_key": "audio_guide"}).json()
    ana.put(f"/api/uploads/{audio['id']}/chunks/0", content=PNG)
    assert ana.post(f"/api/uploads/{audio['id']}/complete").status_code == 422


# ---- jobs, policy and queue -------------------------------------------------------------------

def test_job_validation_and_one_active_job_per_student(app, hub):
    add_user(hub, "ana"); add_worker(hub, "pc-01")
    ana = login(app, "ana")
    assert ana.post("/api/jobs", json={**JOB, "task": "video.generate"}).status_code == 422
    assert ana.post("/api/jobs", json={**JOB, "parameters": {"evil": 1}}).status_code == 422
    assert ana.post("/api/jobs", json={**JOB, "parameters": {"resolution": "4096x4096"}}).status_code == 422
    assert ana.post("/api/jobs", json={**JOB, "parameters": {"num_inference_steps": 500}}).status_code == 422
    assert ana.post("/api/jobs", json={**JOB, "model": "vace_14B", "task": "image.generate"}).status_code == 409  # not installed anywhere
    assert ana.post("/api/jobs", json=JOB).status_code == 200
    assert ana.post("/api/jobs", json=JOB).status_code == 429


def test_admin_policy_disables_models(app, hub):
    add_user(hub, "profe", role="admin"); add_user(hub, "ana"); add_worker(hub, "pc-01")
    admin, ana = login(app, "profe"), login(app, "ana")
    policy = admin.get("/api/admin/policy").json()["policy"]
    policy["enabled_models"] = ["ti2v_2_2"]
    assert admin.put("/api/admin/policy", json=policy).status_code == 200
    assert ana.post("/api/jobs", json=JOB).status_code == 403
    assert ana.get("/api/admin/policy").status_code == 403


def test_queue_positions_fifo_and_wait_estimates(app, hub):
    add_worker(hub, "pc-01")
    clients = []
    for name in ("ana", "beto", "caro"):
        add_user(hub, name); clients.append(login(app, name))
    jobs = [client.post("/api/jobs", json=JOB).json() for client in clients]
    assert [job["queue"]["position"] for job in jobs] == [1, 2, 3]
    third = clients[2].get("/api/state").json()
    assert third["jobs"][0]["queue"]["position"] == 3
    assert third["jobs"][0]["queue"]["estimated_wait_seconds"] == 240  # two image jobs ahead, 120 s each, one PC
    assert third["room"] == {"queued_total": 3, "running_total": 0, "workers_online": 1, "workers_busy": 0}


def test_state_supports_etag_revalidation(app, hub):
    add_user(hub, "ana"); ana = login(app, "ana")
    first = ana.get("/api/state")
    second = ana.get("/api/state", headers={"If-None-Match": first.headers["etag"]})
    assert second.status_code == 304 and second.content == b""


# ---- workers ----------------------------------------------------------------------------------

def test_worker_auth(app, hub):
    add_worker(hub, "pc-01")
    with make_client(app) as client:
        assert client.post("/worker-api/claim", json={"state": {}}).status_code == 401
        assert client.post("/worker-api/claim", json={"state": {}}, headers=worker_headers("bad")).status_code == 401
        assert client.post("/worker-api/claim", json={"state": {}}, headers=worker_headers("token-pc-01")).status_code == 204
    # Requests that came through Cloudflare (loopback peer + CF headers) never reach the worker API, even with a valid token.
    with make_client(app, peer="127.0.0.1") as local:
        assert local.post("/worker-api/claim", json={"state": {}}, headers=worker_headers("token-pc-01")).status_code == 204
        tunneled = local.post("/worker-api/claim", json={"state": {}}, headers={**worker_headers("token-pc-01"), "CF-Connecting-IP": "1.2.3.4"})
        assert tunneled.status_code == 403


def test_worker_state_survives_idle_heartbeats(app, hub):
    token = add_worker(hub, "pc-01")
    with make_client(app) as worker:
        worker.post("/worker-api/claim", json={"state": {"gpu": {"name": "RTX 2060"}, "loaded_model": "z_image", "installed_models": ["z_image"]}}, headers=worker_headers(token))
    hub.scheduler.touch_worker("pc-01", "10.0.0.2")
    row = hub.db.one("SELECT * FROM workers WHERE id='pc-01'")
    assert row["loaded_model"] == "z_image" and "RTX 2060" in row["gpu_json"]


def test_session_endpoint_answers_without_login(client):
    assert client.get("/api/session").json() == {"user": None}


def test_worker_only_receives_models_it_has(app, hub):
    add_user(hub, "ana"); add_worker(hub, "pc-01", installed=["ti2v_2_2"]); add_worker(hub, "pc-02", installed=["z_image"])
    ana = login(app, "ana")
    job = ana.post("/api/jobs", json=JOB).json()
    with make_client(app) as worker:
        assert worker.post("/worker-api/claim", json={"state": {"installed_models": ["ti2v_2_2"]}}, headers=worker_headers("token-pc-01")).status_code == 204
        claimed = worker.post("/worker-api/claim", json={"state": {"installed_models": ["z_image"]}}, headers=worker_headers("token-pc-02"))
        assert claimed.json()["id"] == job["id"]


def test_affinity_prefers_warm_model_within_window(app, hub):
    add_worker(hub, "pc-01")
    ana_id, beto_id = add_user(hub, "ana"), add_user(hub, "beto")
    first = hub.scheduler.submit(ana_id, {"model": "ti2v_2_2", "task": "video.generate", "prompt": "", "inputs": {}, "parameters": {}})
    second = hub.scheduler.submit(beto_id, {"model": "z_image", "task": "image.generate", "prompt": "", "inputs": {}, "parameters": {}})
    hub.db.execute("UPDATE workers SET loaded_model='z_image' WHERE id='pc-01'")
    assert hub.scheduler.claim("pc-01")["id"] == second
    hub.db.execute("UPDATE jobs SET status='succeeded' WHERE id=?", (second,))
    assert hub.scheduler.claim("pc-01")["id"] == first


def test_lost_worker_job_is_requeued_then_failed(app, hub, settings):
    add_user(hub, "ana"); add_worker(hub, "pc-01"); add_worker(hub, "pc-02")
    ana = login(app, "ana")
    job = ana.post("/api/jobs", json=JOB).json()
    assert hub.scheduler.claim("pc-01")["id"] == job["id"]
    hub.db.execute("UPDATE jobs SET lease_expires_at=? WHERE id=?", (time.time() - 1, job["id"]))
    hub.scheduler.reap()
    assert ana.get("/api/state").json()["jobs"][0]["status"] == "queued"
    assert hub.scheduler.claim("pc-02")["id"] == job["id"]
    hub.db.execute("UPDATE jobs SET lease_expires_at=? WHERE id=?", (time.time() - 1, job["id"]))
    hub.scheduler.reap()
    final = ana.get("/api/state").json()["jobs"][0]
    assert final["status"] == "failed" and "dejó de responder" in final["error"]


def test_restarted_worker_releases_its_previous_job(app, hub):
    add_user(hub, "ana"); add_worker(hub, "pc-01")
    ana = login(app, "ana")
    job = ana.post("/api/jobs", json=JOB).json()
    hub.scheduler.claim("pc-01")
    # The agent restarted and claims again: the lost job is put back and handed out again.
    assert hub.scheduler.claim("pc-01")["id"] == job["id"]
    assert hub.db.one("SELECT attempts FROM jobs WHERE id=?", (job["id"],))["attempts"] == 2


def test_cancel_running_job_reaches_worker(app, hub):
    add_user(hub, "ana"); token = add_worker(hub, "pc-01")
    ana = login(app, "ana")
    job = ana.post("/api/jobs", json=JOB).json()
    with make_client(app) as worker:
        worker.post("/worker-api/claim", json={"state": {}}, headers=worker_headers(token))
        assert worker.post(f"/worker-api/jobs/{job['id']}/progress", json={"progress": 40, "phase": "inference"}, headers=worker_headers(token)).json() == {"cancel": False}
        ana.post(f"/api/jobs/{job['id']}/cancel")
        assert worker.post(f"/worker-api/jobs/{job['id']}/progress", json={"progress": 50}, headers=worker_headers(token)).json() == {"cancel": True}
        worker.post(f"/worker-api/jobs/{job['id']}/complete", json={"status": "cancelled"}, headers=worker_headers(token))
    assert ana.get("/api/state").json()["jobs"][0]["status"] == "cancelled"


def test_worker_cannot_touch_jobs_of_other_workers(app, hub):
    add_user(hub, "ana"); add_worker(hub, "pc-01"); other = add_worker(hub, "pc-02")
    ana = login(app, "ana")
    job = ana.post("/api/jobs", json=JOB).json()
    hub.scheduler.claim("pc-01")
    with make_client(app) as worker:
        assert worker.put(f"/worker-api/jobs/{job['id']}/artifacts", params={"name": "x.png"}, content=PNG, headers=worker_headers(other)).status_code == 409
        assert worker.post(f"/worker-api/jobs/{job['id']}/progress", json={}, headers=worker_headers(other)).json() == {"cancel": True}
        assert worker.put(f"/worker-api/jobs/{job['id']}/artifacts", params={"name": "x.svg"}, content=b"<svg/>", headers=worker_headers("token-pc-01")).status_code == 422


# ---- admin ----------------------------------------------------------------------------------

def test_admin_endpoints_require_admin_and_lan_in_tunnel_mode(tmp_path):
    from hub.app.config import HubSettings
    from hub.app.main import create_app
    app = create_app(HubSettings(_env_file=None, mode="tunnel", data_dir=tmp_path / "t", ui_dir=tmp_path / "x"))
    add_user(app.state.hub, "profe", role="admin"); add_user(app.state.hub, "ana")
    with make_client(app, peer="127.0.0.1", https=True) as client:
        assert client.post("/api/auth/login", json={"username": "profe", "password": "password-123"}, headers={"CF-Connecting-IP": "200.1.1.1"}).status_code == 200
        assert client.get("/api/admin/overview", headers={"CF-Connecting-IP": "200.1.1.1"}).status_code == 403
    with make_client(app, peer="192.168.10.5", https=True) as client:
        client.post("/api/auth/login", json={"username": "profe", "password": "password-123"})
        assert client.get("/api/admin/overview").status_code == 200
    with make_client(app, https=True) as ana:
        ana.post("/api/auth/login", json={"username": "ana", "password": "password-123"})
        assert ana.get("/api/admin/overview").status_code == 403


def test_admin_manages_users_and_workers(app, hub):
    add_user(hub, "profe", role="admin")
    admin = login(app, "profe")
    bulk = admin.post("/api/admin/users/bulk", json={"usernames": ["alumno1", "alumno2", "alumno1"]}).json()["created"]
    assert [item["username"] for item in bulk] == ["alumno1", "alumno2"]
    student = login(app, "alumno1", bulk[0]["password"])
    assert student.get("/api/me").status_code == 200
    user_id = student.get("/api/me").json()["user"]["id"]
    admin.patch(f"/api/admin/users/{user_id}", json={"disabled": True})
    assert student.get("/api/me").status_code == 401
    created = admin.post("/api/admin/workers", json={"id": "pc-05"}).json()
    with make_client(app) as worker:
        assert worker.post("/worker-api/claim", json={"state": {}}, headers=worker_headers(created["token"])).status_code == 204
    assert admin.get("/api/admin/workers").json()["workers"][0]["online"] is True
    actions = [event["action"] for event in admin.get("/api/admin/audit").json()["events"]]
    assert "worker_created" in actions and "users_bulk_created" in actions


def test_retention_cleanup_removes_old_jobs_and_files(app, hub):
    from hub.app.main import cleanup_expired
    add_user(hub, "ana"); token = add_worker(hub, "pc-01")
    ana = login(app, "ana")
    job = ana.post("/api/jobs", json=JOB).json()
    with make_client(app) as worker:
        worker.post("/worker-api/claim", json={"state": {}}, headers=worker_headers(token))
        worker.put(f"/worker-api/jobs/{job['id']}/artifacts", params={"name": "o.png"}, content=PNG, headers=worker_headers(token))
        worker.post(f"/worker-api/jobs/{job['id']}/complete", json={"status": "succeeded"}, headers=worker_headers(token))
    path = hub.db.one("SELECT path FROM artifacts")["path"]
    hub.db.execute("UPDATE jobs SET finished_at=?", (time.time() - 30 * 86400,))
    cleanup_expired(hub)
    import os
    assert not os.path.exists(path) and ana.get("/api/state").json()["jobs"] == []


def test_worker_and_admin_networks_are_enforced(tmp_path):
    from hub.app.config import HubSettings
    from hub.app.main import create_app
    app = create_app(HubSettings(_env_file=None, data_dir=tmp_path / "n", ui_dir=tmp_path / "x", claim_wait_seconds=0,
                                 worker_networks="10.20.30.0/24", admin_networks="10.20.30.0/24"))
    add_worker(app.state.hub, "pc-01"); add_user(app.state.hub, "profe", role="admin")
    for peer, expected in (("10.20.30.7", 204), ("127.0.0.1", 204), ("192.168.1.9", 403)):
        with make_client(app, peer=peer) as client:
            assert client.post("/worker-api/claim", json={"state": {}}, headers=worker_headers("token-pc-01")).status_code == expected
    for peer, expected in (("10.20.30.7", 200), ("127.0.0.1", 200), ("192.168.1.9", 403)):
        with make_client(app, peer=peer) as client:
            client.post("/api/auth/login", json={"username": "profe", "password": "password-123"})
            assert client.get("/api/admin/overview").status_code == expected


def test_media_sniffing():
    from hub.app.security import sniff_media
    assert sniff_media(b"\xff\xd8\xff\xe0" + b"\x00" * 20) == {"image"}
    assert sniff_media(b"RIFF\x00\x00\x00\x00WAVEfmt ") == {"audio"}
    assert sniff_media(b"\x00\x00\x00\x18ftypisom\x00\x00") == {"video", "audio"}
    assert sniff_media(b"\x00\x00\x00\x18ftypM4A \x00\x00") == {"audio"}
    assert sniff_media(b"ID3\x04\x00") == {"audio"}
    assert sniff_media(b"<svg xmlns=") == set()
    assert sniff_media(b"MZ\x90\x00") == set()  # executables are never accepted
