from __future__ import annotations

from datetime import date

from sqlalchemy import and_, or_, select

from app.models.quick_note import QuickNote
from app.models.reminder import Tag
from app.repositories.base import BaseRepository

# Sort keys exposed to the API → model columns (whitelist, avoids arbitrary attr access).
_SORTS = {
    "created_at": QuickNote.created_at,
    "updated_at": QuickNote.updated_at,
    "due_date": QuickNote.due_date,
    "title": QuickNote.title,
}


class QuickNoteRepository(BaseRepository[QuickNote]):
    model = QuickNote

    def get_for_user(self, note_id: int, user_id: int) -> QuickNote | None:
        stmt = select(QuickNote).where(
            and_(QuickNote.id == note_id, QuickNote.user_id == user_id))
        return self.db.execute(stmt).scalar_one_or_none()

    def query(self, user_id: int, *, status: str | None = None, category: str | None = None,
              priority: str | None = None, tag: str | None = None, search: str | None = None,
              due_from: date | None = None, due_to: date | None = None,
              include_deleted: bool = False,
              sort: str = "created_at", order: str = "desc",
              limit: int = 50, offset: int = 0) -> list[QuickNote]:
        stmt = select(QuickNote).where(QuickNote.user_id == user_id)
        if not include_deleted:
            stmt = stmt.where(QuickNote.status != "deleted")
        if status:
            stmt = stmt.where(QuickNote.status == status)
        if category:
            stmt = stmt.where(QuickNote.category == category)
        if priority:
            stmt = stmt.where(QuickNote.priority == priority)
        if due_from:
            stmt = stmt.where(QuickNote.due_date >= due_from)
        if due_to:
            stmt = stmt.where(QuickNote.due_date <= due_to)
        if tag:
            stmt = stmt.where(QuickNote.tags.any(and_(Tag.user_id == user_id, Tag.name == tag)))
        if search:
            like = f"%{search.lower()}%"
            stmt = stmt.where(or_(
                QuickNote.title.ilike(like),
                QuickNote.note_text.ilike(like),
                QuickNote.category.ilike(like),
                QuickNote.tags.any(Tag.name.ilike(like)),
            ))
        sort_col = _SORTS.get(sort, QuickNote.created_at)
        stmt = stmt.order_by(sort_col.desc() if order == "desc" else sort_col.asc())
        stmt = stmt.limit(min(limit, 200)).offset(offset)
        return list(self.db.execute(stmt).scalars().unique().all())

    def get_or_create_tag(self, user_id: int, name: str) -> Tag:
        name = name.strip()
        tag = self.db.execute(
            select(Tag).where(and_(Tag.user_id == user_id, Tag.name == name))
        ).scalar_one_or_none()
        if not tag:
            tag = Tag(user_id=user_id, name=name)
            self.db.add(tag)
            self.db.flush()
        return tag
