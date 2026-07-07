"""Quick Notes — lightweight capture that can later be converted into a full Reminder.

Reuses the shared per-user `Tag` model (via the `quick_note_tags` association) so tags
are consistent across reminders and notes.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (Boolean, Column, Date, DateTime, ForeignKey, Index,
                        String, Table, Text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


quick_note_tags = Table(
    "quick_note_tags", Base.metadata,
    Column("note_id", ForeignKey("quick_notes.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class QuickNote(Base):
    __tablename__ = "quick_notes"
    __table_args__ = (
        Index("ix_quicknote_user_status", "user_id", "status"),
        Index("ix_quicknote_due", "due_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # Notes-first: every note lives in a notebook (nullable during migration, then backfilled).
    notebook_id: Mapped[int | None] = mapped_column(
        ForeignKey("notebooks.id", ondelete="SET NULL"), index=True)

    title: Mapped[str | None] = mapped_column(String(255))          # optional
    note_text: Mapped[str] = mapped_column(Text, nullable=False)    # required
    category: Mapped[str] = mapped_column(String(64), default="Personal")
    priority: Mapped[str] = mapped_column(String(16), default="medium")
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)

    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)

    due_date: Mapped[date | None] = mapped_column(Date)             # optional
    due_time: Mapped[str | None] = mapped_column(String(5))         # "HH:MM", optional
    repeat: Mapped[str | None] = mapped_column(String(16))          # none/daily/weekly/monthly/yearly

    # Reminder linkage (set once converted).
    reminder_id: Mapped[int | None] = mapped_column(
        ForeignKey("reminders.id", ondelete="SET NULL"), index=True)

    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    tags: Mapped[list["Tag"]] = relationship(  # noqa: F821
        secondary=quick_note_tags, lazy="selectin")
