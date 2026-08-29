from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.db_types import UTCDateTime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Agent(Base):
    """A saved research-agent configuration. Template-specific shape lives entirely
    in the JSON columns — adding a new template never requires a new column here."""
    __tablename__ = "agents"
    __table_args__ = (
        Index("ix_agent_template_status", "template_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    visibility: Mapped[str] = mapped_column(String(16), default="private")  # private|shared
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)  # active|paused|archived
    tags: Mapped[str] = mapped_column(Text, default="[]")  # JSON list[str]
    result_language: Mapped[str] = mapped_column(String(16), default="en")
    time_zone: Mapped[str] = mapped_column(String(64), default="UTC")

    filters_json: Mapped[str] = mapped_column(Text, default="{}")
    profile_json: Mapped[str | None] = mapped_column(Text)
    schedule_json: Mapped[str] = mapped_column(Text, default='{"mode":"manual"}')
    is_schedule_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    last_run_id: Mapped[int | None] = mapped_column(Integer)
    last_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_run_status: Mapped[str | None] = mapped_column(String(16))
    next_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow, onupdate=_utcnow)

    runs: Mapped[list["AgentRun"]] = relationship(back_populates="agent", cascade="all, delete-orphan")  # noqa: F821
    results: Mapped[list["Result"]] = relationship(back_populates="agent", cascade="all, delete-orphan")  # noqa: F821
    alert_rules: Mapped[list["AlertRule"]] = relationship(back_populates="agent", cascade="all, delete-orphan")  # noqa: F821
    access_grants: Mapped[list["AgentAccess"]] = relationship(back_populates="agent", cascade="all, delete-orphan")  # noqa: F821
