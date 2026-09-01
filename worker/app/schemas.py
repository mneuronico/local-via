from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


class UploadCreate(BaseModel):
    name: str
    size: int = Field(ge=0)
    media_type: str = "application/octet-stream"


class UploadComplete(BaseModel):
    chunks: int = Field(ge=1)


class JobCreate(BaseModel):
    project_id: str = "default"
    model: str
    task: str
    prompt: str = ""
    inputs: dict[str, str | list[str]] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)


class ArtifactOut(BaseModel):
    id: str
    name: str
    media_type: str
    size: int
    url: str


class JobOut(BaseModel):
    id: str
    project_id: str
    model: str
    task: str
    prompt: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    progress: int
    phase: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    parameters: dict[str, Any]
    artifacts: list[ArtifactOut] = Field(default_factory=list)
