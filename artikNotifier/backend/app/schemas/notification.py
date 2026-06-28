from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    reminder_id: int | None
    channel: str
    title: str
    body: str | None
    status: str
    is_read: bool
    created_at: datetime
    sent_at: datetime | None
    read_at: datetime | None


class BellOut(BaseModel):
    unread_count: int
    due_count: int
    overdue_count: int
    recent: list[NotificationOut]


class PreferencesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    theme: str
    default_channels: str
    email_notifications: bool
    in_app_notifications: bool
    digest_enabled: bool


class PreferencesUpdate(BaseModel):
    theme: str | None = None
    default_channels: str | None = None
    email_notifications: bool | None = None
    in_app_notifications: bool | None = None
    digest_enabled: bool | None = None
