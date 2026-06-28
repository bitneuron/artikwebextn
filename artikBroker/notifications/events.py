"""Event semantics: terminal states, severity mapping, and payload construction for
the centralized Artik Notifier API. Pure functions — easy to unit-test."""
from __future__ import annotations

from datetime import datetime

from .schemas import AgentEvent

# Terminal states that trigger a notification.
TERMINAL_STATES = {"completed", "failed", "cancelled", "timeout", "skipped"}

# Agent status → notification severity (per spec).
SEVERITY = {
    "completed": "success",
    "failed": "error",
    "cancelled": "warning",
    "timeout": "error",
    "skipped": "info",
}

# Loose inputs from various agents/runners → a canonical terminal state.
_ALIASES = {
    "success": "completed", "ok": "completed", "done": "completed",
    "complete": "completed", "partial": "completed",
    "error": "failed", "fail": "failed",
    "timed_out": "timeout", "canceled": "cancelled",
}


def normalize_status(raw: str | None) -> str:
    s = (raw or "").strip().lower()
    if s in TERMINAL_STATES:
        return s
    return _ALIASES.get(s, "completed")


def severity_for(status: str) -> str:
    return SEVERITY.get((status or "").lower(), "info")


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def compute_duration(started_at: str | None, completed_at: str | None) -> float | None:
    a, b = _parse(started_at), _parse(completed_at)
    if a and b:
        return max(0.0, (b - a).total_seconds())
    return None


def _title(app_name: str, status: str) -> str:
    nice = {"completed": "Completed", "failed": "Failed", "cancelled": "Cancelled",
            "timeout": "Timed Out", "skipped": "Skipped"}.get(status, status.capitalize())
    return f"{app_name} Agent {nice}"


def _message(agent_name: str, status: str) -> str:
    if status == "completed":
        return f"The {agent_name} completed successfully."
    if status == "failed":
        return f"The {agent_name} failed."
    return f"The {agent_name} {status}."


def build_payload(event: AgentEvent, app_name: str, channel: str = "#artik-notify") -> dict:
    """Build the exact payload the Artik Notifier `/api/v1/notifications/slack` expects."""
    status = normalize_status(event.status)
    duration = (event.duration_seconds if event.duration_seconds is not None
                else compute_duration(event.started_at, event.completed_at))
    return {
        "source_app": app_name,
        "event_type": f"agent_{status}",
        "severity": severity_for(status),
        "title": _title(app_name, status),
        "message": _message(event.agent_name, status),
        "channel": channel,
        "metadata": {
            "agent_name": event.agent_name,
            "agent_id": event.agent_id,
            "job_id": event.job_id,
            "task_name": event.task_name,
            "status": status,
            "started_at": event.started_at,
            "completed_at": event.completed_at,
            "duration_seconds": round(duration, 3) if duration is not None else None,
            "error_message": event.error_message,
            "environment": event.environment,
            "version": event.version,
            "job_url": event.job_url,
        },
    }
