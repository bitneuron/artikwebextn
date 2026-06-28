from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, or_, select

from app.models.reminder import Reminder, Tag
from app.repositories.base import BaseRepository


class ReminderRepository(BaseRepository[Reminder]):
    model = Reminder

    def get_for_user(self, reminder_id: int, user_id: int) -> Reminder | None:
        stmt = select(Reminder).where(
            and_(Reminder.id == reminder_id, Reminder.user_id == user_id))
        return self.db.execute(stmt).scalar_one_or_none()

    def query(self, user_id: int, *, status: str | None = None, category: str | None = None,
              priority: str | None = None, search: str | None = None,
              include_deleted: bool = False,
              sort: str = "due_at", order: str = "asc",
              limit: int = 100, offset: int = 0) -> list[Reminder]:
        stmt = select(Reminder).where(Reminder.user_id == user_id)
        if not include_deleted:
            stmt = stmt.where(Reminder.status != "deleted")
        if status:
            stmt = stmt.where(Reminder.status == status)
        if category:
            stmt = stmt.where(Reminder.category == category)
        if priority:
            stmt = stmt.where(Reminder.priority == priority)
        if search:
            like = f"%{search.lower()}%"
            stmt = stmt.where(or_(
                Reminder.title.ilike(like),
                Reminder.description.ilike(like),
                Reminder.notes.ilike(like),
            ))
        sort_col = getattr(Reminder, sort, Reminder.due_at)
        stmt = stmt.order_by(sort_col.desc() if order == "desc" else sort_col.asc())
        stmt = stmt.limit(limit).offset(offset)
        return list(self.db.execute(stmt).scalars().all())

    def due_between(self, start: datetime, end: datetime) -> list[Reminder]:
        stmt = select(Reminder).where(and_(
            Reminder.due_at >= start, Reminder.due_at <= end,
            Reminder.status.in_(["active", "snoozed"])))
        return list(self.db.execute(stmt).scalars().all())

    def get_or_create_tag(self, user_id: int, name: str) -> Tag:
        name = name.strip()
        stmt = select(Tag).where(and_(Tag.user_id == user_id, Tag.name == name))
        tag = self.db.execute(stmt).scalar_one_or_none()
        if not tag:
            tag = Tag(user_id=user_id, name=name)
            self.db.add(tag)
            self.db.flush()
        return tag
