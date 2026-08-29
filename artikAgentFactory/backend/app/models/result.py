from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.db_types import UTCDateTime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Result(Base):
    """A single research finding. Shape-agnostic across all templates: fixed columns
    hold the fields every finding needs (title/summary/url/scores/dedup identity);
    `fields_json` holds whatever template-specific payload applies (deadline, price,
    ticker, etc.) — no per-template table, per the platform's core design rule."""
    __tablename__ = "results"
    __table_args__ = (
        UniqueConstraint("agent_id", "dedup_key", name="uq_result_agent_dedup"),
        Index("ix_result_agent_status", "agent_id", "change_status"),
        Index("ix_result_agent_category", "agent_id", "category"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    first_seen_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"))
    last_seen_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"))

    dedup_key: Mapped[str] = mapped_column(String(128), nullable=False)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    source_name: Mapped[str | None] = mapped_column(String(255))
    published_or_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    source_credibility: Mapped[str] = mapped_column(String(16), default="medium")  # high|medium|low

    category: Mapped[str] = mapped_column(String(64), default="general", index=True)
    fields_json: Mapped[str] = mapped_column(Text, default="{}")

    change_status: Mapped[str] = mapped_column(String(16), default="new")  # new|changed|unchanged
    changed_fields_json: Mapped[str | None] = mapped_column(Text)

    is_saved: Mapped[bool] = mapped_column(Boolean, default=False)
    is_dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
    priority_flag: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow, onupdate=_utcnow)

    agent: Mapped["Agent"] = relationship(back_populates="results")  # noqa: F821
    sources: Mapped[list["ResultSource"]] = relationship(back_populates="result", cascade="all, delete-orphan")
    notes: Mapped[list["Note"]] = relationship(back_populates="result", cascade="all, delete-orphan")  # noqa: F821


class ResultSource(Base):
    """Corroborating sources beyond the primary `url` — traceability/audit trail."""
    __tablename__ = "result_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("results.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    retrieved_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)
    snippet: Mapped[str | None] = mapped_column(Text)

    result: Mapped["Result"] = relationship(back_populates="sources")
