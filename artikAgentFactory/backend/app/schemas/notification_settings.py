from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class NotificationSettingsOut(BaseModel):
    workspace_id: int
    slack_enabled: bool
    notify_on_run_completed: bool
    notify_on_new_results: bool
    notify_on_changed_results: bool
    notify_on_high_priority: bool
    notify_on_deadline_approaching: bool
    notify_on_run_error: bool
    min_severity: str
    slack_configured: bool
    updated_at: datetime


class NotificationSettingsUpdate(BaseModel):
    slack_enabled: bool | None = None
    notify_on_run_completed: bool | None = None
    notify_on_new_results: bool | None = None
    notify_on_changed_results: bool | None = None
    notify_on_high_priority: bool | None = None
    notify_on_deadline_approaching: bool | None = None
    notify_on_run_error: bool | None = None
    min_severity: str | None = None
