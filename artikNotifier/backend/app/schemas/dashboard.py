from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.notification import NotificationOut
from app.schemas.reminder import ReminderOut


class DashboardOut(BaseModel):
    counts: dict[str, int]               # upcoming, due_today, overdue, completed, unread
    due_today: list[ReminderOut]
    overdue: list[ReminderOut]
    upcoming: list[ReminderOut]
    recent_activity: list[NotificationOut]


class CalendarDay(BaseModel):
    date: date
    reminders: list[ReminderOut]


class CalendarOut(BaseModel):
    month: int
    year: int
    days: list[CalendarDay]


class Message(BaseModel):
    detail: str
