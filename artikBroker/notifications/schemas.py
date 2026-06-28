"""Standard internal event model for Artik Broker agent notifications."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AgentEvent:
    """A terminal-state event for any Artik Broker agent. Generic by design — every
    agent (current and future) produces one of these, so no per-agent code is needed."""
    agent_name: str
    status: str                       # completed | failed | cancelled | timeout | skipped
    agent_id: str | None = None
    job_id: str | None = None
    task_name: str | None = None
    started_at: str | None = None     # ISO-8601
    completed_at: str | None = None   # ISO-8601
    duration_seconds: float | None = None
    error_message: str | None = None
    environment: str | None = None
    version: str | None = None
    job_url: str | None = None
