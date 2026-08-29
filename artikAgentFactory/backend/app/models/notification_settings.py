from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.db_types import UTCDateTime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class NotificationSettings(Base):
    """One row per workspace. Admin-editable workspace-wide Slack kill switch /
    severity floor, layered on top of each agent's own AlertRule configuration."""
    __tablename__ = "notification_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), unique=True, nullable=False)
    slack_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_on_run_completed: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_on_new_results: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_on_changed_results: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_on_high_priority: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_on_deadline_approaching: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_on_run_error: Mapped[bool] = mapped_column(Boolean, default=True)
    min_severity: Mapped[str] = mapped_column(String(16), default="info")  # info|warning|error
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow, onupdate=_utcnow)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
