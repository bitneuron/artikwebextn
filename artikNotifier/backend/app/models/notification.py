from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class NotificationRule(Base):
    """A concrete scheduled fire-time for a reminder (one per schedule offset).
    The scheduler reads these; `dedupe_key` guarantees a rule fires at most once."""
    __tablename__ = "notification_rules"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_rule_dedupe"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    reminder_id: Mapped[int] = mapped_column(ForeignKey("reminders.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    offset_key: Mapped[str] = mapped_column(String(32))      # e.g. "1_week"
    fire_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    channels: Mapped[str] = mapped_column(Text, default='["email","in_app"]')
    fired: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    dedupe_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notif_user_status", "user_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    reminder_id: Mapped[int | None] = mapped_column(ForeignKey("reminders.id", ondelete="SET NULL"), index=True)
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("notification_rules.id", ondelete="SET NULL"))

    channel: Mapped[str] = mapped_column(String(16), default="in_app")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    dedupe_key: Mapped[str | None] = mapped_column(String(160), index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    reminder: Mapped["Reminder | None"] = relationship(back_populates="notifications")  # noqa: F821


class NotificationHistory(Base):
    """Per-delivery-attempt log (provider, status, error) for observability."""
    __tablename__ = "notification_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    notification_id: Mapped[int] = mapped_column(ForeignKey("notifications.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
