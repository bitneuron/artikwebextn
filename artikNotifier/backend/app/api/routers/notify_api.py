"""Centralized cross-app notifications API.

Other Artik applications (e.g. artikBroker) POST events here with an API key; this
service formats them and forwards to Slack (#artik-notify) via the shared webhook —
so the whole ecosystem uses one notification system instead of each app talking to
Slack directly. Every call is audit-logged (API keys are never logged).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.logging_config import log_event
from app.models.system import AuditLog
from app.notifications.providers import post_slack
from app.schemas.notify import NotifyResult, SlackNotifyIn

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications-api"])

_EMOJI = {"success": "✅", "error": "❌", "warning": "⚠️", "info": "ℹ️"}


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> str:
    keys = settings.notify_api_key_set
    if not keys:
        raise HTTPException(503, "notifications API is not configured (no API keys)")
    if not x_api_key or x_api_key not in keys:
        raise HTTPException(401, "invalid or missing API key")
    return x_api_key


def _fmt_duration(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    s = int(seconds)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def build_slack_text(p: SlackNotifyIn) -> str:
    """Render a payload into a readable Slack message (mrkdwn)."""
    md = p.metadata
    emoji = _EMOJI.get((p.severity or "info").lower(), "ℹ️")
    head = f"{emoji} *{p.title}*"
    lines: list[str] = []

    def add(label: str, val) -> None:
        if val not in (None, ""):
            lines.append(f"*{label}:* {val}")

    add("Agent", md.agent_name)
    add("Task", md.task_name)
    add("Status", md.status)
    add("Duration", _fmt_duration(md.duration_seconds))
    add("Environment", md.environment)
    add("Job ID", md.job_id)
    if md.error_message and (p.severity or "").lower() in ("error", "warning"):
        lines.append(f"*Error:* {md.error_message}")
    if not lines and p.message:           # no metadata → fall back to the message
        lines.append(p.message)
    body = "\n".join(lines)
    text = f"{head}\n\n{body}" if body else head
    if md.job_url:
        text += f"\n\n<{md.job_url}|View Job>"
    return text


@router.post("/slack", response_model=NotifyResult)
def slack_notify(body: SlackNotifyIn, _key: str = Depends(require_api_key),
                 db: Session = Depends(get_db)):
    ok, detail = post_slack(build_slack_text(body))
    # Audit the inbound event (never the API key).
    db.add(AuditLog(
        user_id=None, action="notify.slack", entity="notification",
        detail=f"src={body.source_app} type={body.event_type} sev={body.severity} "
               f"agent={body.metadata.agent_name} ok={ok} {detail}"[:500]))
    db.commit()
    log_event("notification", "cross-app slack", source=body.source_app,
              event=body.event_type, severity=body.severity, ok=ok, detail=detail)
    return {"ok": ok, "detail": detail}
