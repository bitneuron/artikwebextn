from __future__ import annotations

from sqlalchemy import and_, or_, select

from app.models.result import Result
from app.repositories.base import BaseRepository


class ResultRepository(BaseRepository[Result]):
    model = Result

    def get_by_dedup_key(self, agent_id: int, dedup_key: str) -> Result | None:
        stmt = select(Result).where(and_(Result.agent_id == agent_id, Result.dedup_key == dedup_key))
        return self.db.execute(stmt).scalar_one_or_none()

    def all_for_agent(self, agent_id: int, *, include_dismissed: bool = True) -> list[Result]:
        stmt = select(Result).where(Result.agent_id == agent_id)
        if not include_dismissed:
            stmt = stmt.where(Result.is_dismissed.is_(False))
        return list(self.db.execute(stmt).scalars().all())

    def query(self, agent_id: int, *, category: str | None = None, change_status: str | None = None,
              is_saved: bool | None = None, is_dismissed: bool | None = None,
              min_relevance: float | None = None, search: str | None = None,
              sort: str = "created_at", order: str = "desc",
              limit: int = 100, offset: int = 0) -> list[Result]:
        stmt = select(Result).where(Result.agent_id == agent_id)
        if category:
            stmt = stmt.where(Result.category == category)
        if change_status:
            stmt = stmt.where(Result.change_status == change_status)
        if is_saved is not None:
            stmt = stmt.where(Result.is_saved.is_(is_saved))
        if is_dismissed is not None:
            stmt = stmt.where(Result.is_dismissed.is_(is_dismissed))
        else:
            stmt = stmt.where(Result.is_dismissed.is_(False))
        if min_relevance is not None:
            stmt = stmt.where(Result.relevance_score >= min_relevance)
        if search:
            like = f"%{search.lower()}%"
            stmt = stmt.where(or_(Result.title.ilike(like), Result.summary.ilike(like)))
        sort_col = getattr(Result, sort, Result.created_at)
        stmt = stmt.order_by(sort_col.desc() if order == "desc" else sort_col.asc())
        stmt = stmt.limit(limit).offset(offset)
        return list(self.db.execute(stmt).scalars().all())
