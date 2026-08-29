from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.db_types import UTCDateTime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AlertRule(Base):
    """A saved condition under which an agent notifies the user. Kept as a real table
    (not folded into agents.alerts_json) so AlertEvent can FK back to which rule fired."""
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # new_results|changed_results|high_priority_match|deadline_approaching|run_error
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    channel: Mapped[str] = mapped_column(String(16), default="in_app")  # slack|in_app
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)

    agent: Mapped["Agent"] = relationship(back_populates="alert_rules")  # noqa: F821


class AlertEvent(Base):
    """A fired alert. rule_id/result_id are nullable for run-level alerts (e.g. run_error)."""
    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("alert_rules.id", ondelete="SET NULL"))
    result_id: Mapped[int | None] = mapped_column(ForeignKey("results.id", ondelete="SET NULL"))
    severity: Mapped[str] = mapped_column(String(16), default="info")  # info|success|warning|error
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, default="")
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)
