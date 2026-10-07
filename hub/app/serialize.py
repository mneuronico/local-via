import json
from datetime import datetime, timezone
from .catalog import MODEL_NAMES


def iso(value: float | None) -> str | None:
    return datetime.fromtimestamp(value, timezone.utc).isoformat() if value else None


def artifact_out(row: dict) -> dict:
    return {"id": row["id"], "name": row["name"], "media_type": row["media_type"], "size": row["size"], "url": f"/api/files/{row['id']}"}


def job_out(row: dict, artifacts: list[dict], queue: dict | None = None, username: str | None = None) -> dict:
    result = {
        "id": row["id"], "model": row["model"], "model_name": MODEL_NAMES.get(row["model"], row["model"]), "task": row["task"],
        "prompt": row["prompt"], "status": row["status"], "progress": row["progress"], "phase": row["phase"], "error": row["error"],
        "worker_id": row["worker_id"] if row["status"] == "running" else None,
        "created_at": iso(row["created_at"]), "updated_at": iso(row["updated_at"]),
        "started_at": iso(row["claimed_at"]), "finished_at": iso(row["finished_at"]),
        "parameters": json.loads(row["parameters_json"]), "artifacts": [artifact_out(item) for item in artifacts],
        "queue": queue,
    }
    if username is not None: result["username"] = username
    return result


def user_out(row: dict) -> dict:
    return {"id": row["id"], "username": row["username"], "display_name": row["display_name"], "role": row["role"],
            "class_id": row.get("class_id"), "disabled": bool(row.get("disabled")), "created_at": iso(row.get("created_at")),
            "last_login_at": iso(row.get("last_login_at"))}


def worker_out(row: dict, online: bool) -> dict:
    return {"id": row["id"], "online": online, "disabled": bool(row["disabled"]), "last_seen_at": iso(row["last_seen_at"]), "ip": row["ip"],
            "backend": row["backend"], "version": row["version"], "loaded_model": row["loaded_model"],
            "gpu": json.loads(row["gpu_json"]) if row["gpu_json"] else None,
            "installed_models": json.loads(row["installed_json"]) if row["installed_json"] else [], "current_job_id": row["current_job_id"]}
