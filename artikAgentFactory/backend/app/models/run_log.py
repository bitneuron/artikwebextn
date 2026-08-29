from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.db_types import UTCDateTime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RunLog(Base):
    """Every message is scrubbed of secrets before insert — see
    services.pipeline.log_scrub.log_run(), the single write path into this table."""
    __tablename__ = "run_logs"
    __table_args__ = (
        Index("ix_runlog_run_ts", "run_id", "ts"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)
    level: Mapped[str] = mapped_column(String(8), default="info")  # info|warn|error
    stage: Mapped[str] = mapped_column(String(32), default="")
    message: Mapped[str] = mapped_column(Text, default="")

    run: Mapped["AgentRun"] = relationship(back_populates="logs")  # noqa: F821
