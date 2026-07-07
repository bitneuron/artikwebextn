"""Notebook — top-level organization for notes (Evernote-style). Every note belongs to one.

Notes-first redesign: notebooks group notes; reminders are integrated into notes rather
than being the primary entity. Per-user, with favorite/archive/default flags.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Notebook(Base):
    __tablename__ = "notebooks"
    __table_args__ = (Index("ix_notebook_user", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    icon: Mapped[str | None] = mapped_column(String(16))          # emoji, optional
    color: Mapped[str | None] = mapped_column(String(16))         # hex/name, optional
    description: Mapped[str | None] = mapped_column(String(500))

    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
