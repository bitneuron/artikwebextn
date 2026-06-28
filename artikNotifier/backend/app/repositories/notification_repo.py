from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, func, select

from app.models.notification import Notification, NotificationRule
from app.repositories.base import BaseRepository


class NotificationRepository(BaseRepository[Notification]):
    model = Notification

    def get_for_user(self, notif_id: int, user_id: int) -> Notification | None:
        stmt = select(Notification).where(
            and_(Notification.id == notif_id, Notification.user_id == user_id))
        return self.db.execute(stmt).scalar_one_or_none()

    def query(self, user_id: int, *, status: str | None = None, unread_only: bool = False,
              search: str | None = None, limit: int = 50, offset: int = 0) -> list[Notification]:
        stmt = select(Notification).where(
            and_(Notification.user_id == user_id, Notification.status != "deleted"))
        if status:
            stmt = stmt.where(Notification.status == status)
        if unread_only:
            stmt = stmt.where(Notification.is_read.is_(False))
        if search:
            like = f"%{search.lower()}%"
            stmt = stmt.where(Notification.title.ilike(like))
        stmt = stmt.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
        return list(self.db.execute(stmt).scalars().all())

    def unread_count(self, user_id: int) -> int:
        stmt = select(func.count()).select_from(Notification).where(and_(
            Notification.user_id == user_id, Notification.is_read.is_(False),
            Notification.status != "deleted"))
        return int(self.db.execute(stmt).scalar() or 0)

    def exists_dedupe(self, dedupe_key: str) -> bool:
        stmt = select(Notification.id).where(Notification.dedupe_key == dedupe_key).limit(1)
        return self.db.execute(stmt).scalar_one_or_none() is not None


class NotificationRuleRepository(BaseRepository[NotificationRule]):
    model = NotificationRule

    def due_rules(self, now: datetime, limit: int = 500) -> list[NotificationRule]:
        stmt = select(NotificationRule).where(and_(
            NotificationRule.fired.is_(False),
            NotificationRule.fire_at <= now)).order_by(NotificationRule.fire_at).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def get_by_dedupe(self, dedupe_key: str) -> NotificationRule | None:
        stmt = select(NotificationRule).where(NotificationRule.dedupe_key == dedupe_key)
        return self.db.execute(stmt).scalar_one_or_none()

    def delete_for_reminder(self, reminder_id: int, only_unfired: bool = True) -> None:
        stmt = select(NotificationRule).where(NotificationRule.reminder_id == reminder_id)
        if only_unfired:
            stmt = stmt.where(NotificationRule.fired.is_(False))
        for r in self.db.execute(stmt).scalars().all():
            self.db.delete(r)
        self.db.flush()
