from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotebookBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    icon: str | None = Field(default=None, max_length=16)
    color: str | None = Field(default=None, max_length=16)
    description: str | None = Field(default=None, max_length=500)


class NotebookCreate(NotebookBase):
    pass


class NotebookUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    icon: str | None = Field(default=None, max_length=16)
    color: str | None = Field(default=None, max_length=16)
    description: str | None = Field(default=None, max_length=500)
    is_favorite: bool | None = None
    is_archived: bool | None = None


class NotebookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    name: str
    icon: str | None
    color: str | None
    description: str | None
    is_favorite: bool
    is_archived: bool
    is_default: bool
    created_at: datetime
    updated_at: datetime
    note_count: int = 0
