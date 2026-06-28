"""Dashboard + calendar aggregations."""
from __future__ import annotations

import calendar as _cal
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.reminder import Reminder
from app.repositories.notification_repo import NotificationRepository
from app.repositories.reminder_repo import ReminderRepository
from app.services.reminder_service import ReminderService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DashboardService:
    def __init__(self, db: Session):
        self.db = db
        self.reminders = ReminderRepository(db)
        self.notifs = NotificationRepository(db)
        self.rsvc = ReminderService(db)

    def _count(self, user_id: int, *conds) -> int:
        stmt = select(func.count()).select_from(Reminder).where(
            and_(Reminder.user_id == user_id, Reminder.status != "deleted", *conds))
        return int(self.db.execute(stmt).scalar() or 0)

    def due_overdue_counts(self, user_id: int) -> tuple[int, int]:
        now = _utcnow()
        day_end = now.replace(hour=23, minute=59, second=59, microsecond=0)
        due_today = self._count(user_id, Reminder.status.in_(["active", "snoozed"]),
                                 Reminder.due_at >= now.replace(hour=0, minute=0, second=0, microsecond=0),
                                 Reminder.due_at <= day_end)
        overdue = self._count(user_id, Reminder.status.in_(["active", "snoozed"]),
                              Reminder.due_at < now)
        return due_today, overdue

    def dashboard(self, user_id: int) -> dict:
        now = _utcnow()
        start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_today = start_today + timedelta(days=1)
        week_ahead = now + timedelta(days=7)

        def out(rs): return [self.rsvc.to_out(r) for r in rs]

        due_today = self.reminders.due_between(start_today, end_today)
        overdue = [r for r in self.reminders.query(user_id, status="active", sort="due_at")
                   if r.due_at and _ensure(r.due_at) < now]
        overdue += [r for r in self.reminders.query(user_id, status="snoozed", sort="due_at")
                    if r.due_at and _ensure(r.due_at) < now]
        upcoming = [r for r in self.reminders.due_between(now, week_ahead) if r.user_id == user_id]

        due_today = [r for r in due_today if r.user_id == user_id]
        completed = self._count(user_id, Reminder.status == "completed")
        upcoming_count = self._count(user_id, Reminder.status.in_(["active", "snoozed"]),
                                     Reminder.due_at >= now)
        due_n, overdue_n = self.due_overdue_counts(user_id)

        return {
            "counts": {
                "upcoming": upcoming_count, "due_today": due_n, "overdue": overdue_n,
                "completed": completed, "unread": self.notifs.unread_count(user_id),
            },
            "due_today": out(due_today),
            "overdue": out(sorted(overdue, key=lambda r: r.due_at)[:20]),
            "upcoming": out(sorted(upcoming, key=lambda r: r.due_at)[:20]),
            "recent_activity": self.notifs.query(user_id, limit=10),
        }

    def calendar(self, user_id: int, year: int, month: int) -> dict:
        first = datetime(year, month, 1, tzinfo=timezone.utc)
        last_day = _cal.monthrange(year, month)[1]
        last = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)
        rems = [r for r in self.reminders.due_between(first, last) if r.user_id == user_id]
        # include completed in calendar view too
        stmt = select(Reminder).where(and_(
            Reminder.user_id == user_id, Reminder.status != "deleted",
            Reminder.due_at >= first, Reminder.due_at <= last))
        rems = list(self.db.execute(stmt).scalars().all())
        by_day: dict[int, list] = {}
        for r in rems:
            by_day.setdefault(_ensure(r.due_at).day, []).append(self.rsvc.to_out(r))
        days = [{"date": datetime(year, month, d).date(), "reminders": by_day.get(d, [])}
                for d in range(1, last_day + 1)]
        return {"month": month, "year": year, "days": days}


def _ensure(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
