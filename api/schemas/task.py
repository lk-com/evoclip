from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TaskCreateResponse(BaseModel):
    task_id: str


class TaskReadResponse(BaseModel):
    id: str
    status: str
    progress: int
    input_video_key: str
    output_video_key: str | None = None
    checkpoint: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
