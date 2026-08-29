from __future__ import annotations

from sqlalchemy import or_, select

from app.models.agent import Agent
from app.repositories.base import BaseRepository


class AgentRepository(BaseRepository[Agent]):
    model = Agent

    def query(self, *, accessible_ids=None, status: str | None = None, template_id: str | None = None,
              search: str | None = None, sort: str = "updated_at", order: str = "desc",
              limit: int = 200, offset: int = 0) -> list[Agent]:
        stmt = select(Agent)
        if accessible_ids is not None:
            stmt = stmt.where(Agent.id.in_(accessible_ids))
        if status:
            stmt = stmt.where(Agent.status == status)
        else:
            stmt = stmt.where(Agent.status != "archived")
        if template_id:
            stmt = stmt.where(Agent.template_id == template_id)
        if search:
            like = f"%{search.lower()}%"
            stmt = stmt.where(or_(Agent.name.ilike(like), Agent.objective.ilike(like)))
        sort_col = getattr(Agent, sort, Agent.updated_at)
        stmt = stmt.order_by(sort_col.desc() if order == "desc" else sort_col.asc())
        stmt = stmt.limit(limit).offset(offset)
        return list(self.db.execute(stmt).scalars().all())

    def active_scheduled(self) -> list[Agent]:
        stmt = select(Agent).where(Agent.status == "active", Agent.is_schedule_enabled.is_(True))
        return list(self.db.execute(stmt).scalars().all())
