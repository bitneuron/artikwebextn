"""All ORM models — importing this package registers every mapper on Base.metadata."""
from app.models.user import User, Session, PasswordReset, UserPreferences
from app.models.reminder import (Category, Tag, Reminder, ReminderHistory, reminder_tags)
from app.models.notification import (NotificationRule, Notification, NotificationHistory)
from app.models.system import EmailTemplate, SchedulerJob, AuditLog
from app.models.chat import ChatMessage
from app.models.quick_note import QuickNote, quick_note_tags

__all__ = [
    "User", "Session", "PasswordReset", "UserPreferences",
    "Category", "Tag", "Reminder", "ReminderHistory", "reminder_tags",
    "NotificationRule", "Notification", "NotificationHistory",
    "EmailTemplate", "SchedulerJob", "AuditLog", "ChatMessage",
    "QuickNote", "quick_note_tags",
]
