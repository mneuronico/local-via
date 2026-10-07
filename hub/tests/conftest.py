import time
import pytest
from fastapi.testclient import TestClient
from hub.app.config import HubSettings
from hub.app.main import create_app
from hub.app.security import hash_password, token_hash

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 120
API = {"X-LocalVia": "1"}


@pytest.fixture
def settings(tmp_path):
    return HubSettings(_env_file=None, data_dir=tmp_path / "hub", ui_dir=tmp_path / "no-ui", claim_wait_seconds=0, lease_seconds=60)


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def hub(app):
    return app.state.hub


def make_client(app, peer: str = "testclient", https: bool = False) -> TestClient:
    client = TestClient(app, client=(peer, 50000), base_url="https://testserver" if https else "http://testserver")
    client.headers.update(API)
    return client


@pytest.fixture
def client(app):
    with make_client(app) as instance:
        yield instance


def add_user(hub, username: str, password: str = "password-123", role: str = "student") -> str:
    import uuid
    user_id = uuid.uuid4().hex
    hub.db.execute("INSERT INTO users (id, username, display_name, password_hash, role, created_at) VALUES (?,?,?,?,?,?)",
                   (user_id, username, username, hash_password(password), role, time.time()))
    return user_id


def add_worker(hub, name: str, installed: list[str] | None = None, token: str | None = None) -> str:
    import json
    token = token or f"token-{name}"
    hub.db.execute("INSERT INTO workers (id, token_hash, created_at, last_seen_at, installed_json) VALUES (?,?,?,?,?)",
                   (name, token_hash(token), time.time(), time.time(), json.dumps(installed if installed is not None else ["z_image", "ti2v_2_2", "qwen_image_edit_plus_20B"])))
    return token


def login(app, username: str, password: str = "password-123") -> TestClient:
    client = make_client(app)
    client.__enter__()
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return client


def upload(client: TestClient, data: bytes = PNG, input_key: str = "image_primary", name: str = "foto.png") -> str:
    created = client.post("/api/uploads", json={"name": name, "size": len(data), "media_type": "image/png", "input_key": input_key})
    assert created.status_code == 200, created.text
    upload_id = created.json()["id"]
    assert client.put(f"/api/uploads/{upload_id}/chunks/0", content=data).status_code == 200
    done = client.post(f"/api/uploads/{upload_id}/complete")
    assert done.status_code == 200, done.text
    return upload_id
