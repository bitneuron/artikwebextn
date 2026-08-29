from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.db_types import UTCDateTime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_run_agent_started", "agent_id", "started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    trigger: Mapped[str] = mapped_column(String(16), default="manual")  # manual|scheduled
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)  # queued|running|completed|failed|partial

    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    duration_seconds: Mapped[float | None] = mapped_column(Float)

    result_count_new: Mapped[int] = mapped_column(Integer, default=0)
    result_count_changed: Mapped[int] = mapped_column(Integer, default=0)
    result_count_unchanged: Mapped[int] = mapped_column(Integer, default=0)
    result_count_total: Mapped[int] = mapped_column(Integer, default=0)

    error_message: Mapped[str | None] = mapped_column(Text)
    queries_json: Mapped[str | None] = mapped_column(Text)
    stats_json: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)

    agent: Mapped["Agent"] = relationship(back_populates="runs")  # noqa: F821
    logs: Mapped[list["RunLog"]] = relationship(back_populates="run", cascade="all, delete-orphan")  # noqa: F821
