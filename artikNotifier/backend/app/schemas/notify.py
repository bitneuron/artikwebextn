"""Schemas for the centralized cross-app notifications API."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class NotifyMetadata(BaseModel):
    """Structured context for an event. Extra keys are allowed (forward-compatible)."""
    model_config = ConfigDict(extra="allow")

    agent_name: str | None = None
    agent_id: str | None = None
    job_id: str | None = None
    task_name: str | None = None
    status: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float | None = None
    environment: str | None = None
    version: str | None = None
    error_message: str | None = None
    job_url: str | None = None


class SlackNotifyIn(BaseModel):
    source_app: str = "unknown"
    event_type: str = "event"
    severity: str = "info"           # success | error | warning | info
    title: str = Field(min_length=1, max_length=255)
    message: str = ""
    channel: str | None = None       # informational; the webhook targets its own channel
    metadata: NotifyMetadata = Field(default_factory=NotifyMetadata)


class NotifyResult(BaseModel):
    ok: bool
    detail: str
