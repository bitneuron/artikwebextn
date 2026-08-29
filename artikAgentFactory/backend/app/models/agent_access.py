from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.db_types import UTCDateTime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgentAccess(Base):
    """Explicit per-agent grant. The sole authority for what a user may do on one
    specific agent beyond ownership/shared-workspace baseline — see auth/access.py."""
    __tablename__ = "agent_access"
    __table_args__ = (UniqueConstraint("agent_id", "user_id", name="uq_agent_access_agent_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    access_level: Mapped[str] = mapped_column(String(16), nullable=False)  # viewer|researcher|manager
    granted_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow, onupdate=_utcnow)

    agent: Mapped["Agent"] = relationship(back_populates="access_grants")  # noqa: F821
