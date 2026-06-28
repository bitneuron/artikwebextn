from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import (Channel, Priority, Recurrence, ReminderStatus,
                              SCHEDULE_OFFSETS_MINUTES)

_VALID_SCHEDULE = set(SCHEDULE_OFFSETS_MINUTES) | {"custom"}


class ReminderBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    notes: str | None = None
    category: str = "Personal"
    priority: Priority = Priority.medium
    due_at: datetime
    timezone: str = "UTC"
    recurrence: Recurrence = Recurrence.one_time
    schedule: list[str] = Field(default_factory=lambda: ["on_due"])
    channels: list[Channel] = Field(
        default_factory=lambda: [Channel.email, Channel.in_app, Channel.slack])
    tags: list[str] = Field(default_factory=list)

    @field_validator("schedule")
    @classmethod
    def _check_schedule(cls, v: list[str]) -> list[str]:
        bad = [s for s in v if s not in _VALID_SCHEDULE]
        if bad:
            raise ValueError(f"invalid schedule offsets: {bad}")
        return v or ["on_due"]


class ReminderCreate(ReminderBase):
    pass


class ReminderUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    notes: str | None = None
    category: str | None = None
    priority: Priority | None = None
    due_at: datetime | None = None
    timezone: str | None = None
    recurrence: Recurrence | None = None
    schedule: list[str] | None = None
    channels: list[Channel] | None = None
    tags: list[str] | None = None
    status: ReminderStatus | None = None


class SnoozeIn(BaseModel):
    minutes: int | None = Field(default=None, ge=1)
    until: datetime | None = None


class ReminderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    title: str
    description: str | None
    notes: str | None
    category: str
    priority: str
    status: str
    due_at: datetime
    timezone: str
    recurrence: str
    schedule: list[str]
    channels: list[str]
    tags: list[str]
    completed_at: datetime | None
    snoozed_until: datetime | None
    created_at: datetime
    updated_at: datetime
