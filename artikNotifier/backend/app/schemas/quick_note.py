from __future__ import annotations

import re
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import Priority, QuickNoteStatus

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")  # "HH:MM" 24h


class QuickNoteBase(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    note_text: str = Field(min_length=1, max_length=10000)
    category: str = "Personal"
    priority: Priority = Priority.medium
    notebook_id: int | None = None
    is_favorite: bool = False
    pinned: bool = False
    due_date: date | None = None
    due_time: str | None = None
    repeat: str | None = None
    tags: list[str] = Field(default_factory=list)

    @field_validator("due_time")
    @classmethod
    def _check_time(cls, v: str | None) -> str | None:
        if v and not _TIME_RE.match(v):
            raise ValueError("due_time must be HH:MM (24-hour)")
        return v


class QuickNoteCreate(QuickNoteBase):
    pass


class QuickNoteUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    note_text: str | None = Field(default=None, min_length=1, max_length=10000)
    category: str | None = None
    priority: Priority | None = None
    notebook_id: int | None = None
    is_favorite: bool | None = None
    pinned: bool | None = None
    due_date: date | None = None
    due_time: str | None = None
    repeat: str | None = None
    tags: list[str] | None = None
    status: QuickNoteStatus | None = None

    @field_validator("due_time")
    @classmethod
    def _check_time(cls, v: str | None) -> str | None:
        if v and not _TIME_RE.match(v):
            raise ValueError("due_time must be HH:MM (24-hour)")
        return v


class QuickNoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    notebook_id: int | None = None
    title: str | None
    note_text: str
    category: str
    priority: str
    status: str
    is_favorite: bool = False
    pinned: bool = False
    due_date: date | None
    due_time: str | None
    repeat: str | None = None
    reminder_id: int | None
    archived: bool
    deleted: bool
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class ConvertResult(BaseModel):
    """Returned by convert-to-reminder: the updated note + the new reminder id."""
    note: QuickNoteOut
    reminder_id: int
