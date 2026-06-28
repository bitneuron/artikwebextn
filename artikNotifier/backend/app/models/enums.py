"""Domain enums (stored as strings for portability / readability)."""
from __future__ import annotations

import enum


class Role(str, enum.Enum):
    user = "user"
    admin = "admin"


class Priority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ReminderStatus(str, enum.Enum):
    active = "active"
    completed = "completed"
    archived = "archived"
    snoozed = "snoozed"
    deleted = "deleted"


class Recurrence(str, enum.Enum):
    one_time = "one_time"
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"
    quarterly = "quarterly"
    yearly = "yearly"


class Channel(str, enum.Enum):
    email = "email"
    in_app = "in_app"
    sms = "sms"
    push = "push"
    slack = "slack"
    teams = "teams"
    discord = "discord"
    whatsapp = "whatsapp"
    webhook = "webhook"


class NotificationStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"
    read = "read"
    archived = "archived"
    deleted = "deleted"


# Default categories seeded for every user / available globally.
DEFAULT_CATEGORIES = [
    "Payment", "Finance", "Investment", "Medical", "Insurance", "Vehicle",
    "Tax", "Subscription", "Family", "Personal", "Business", "Education",
    "Shopping", "Custom",
]

# Offsets (in minutes before due) for the reminder schedule presets.
SCHEDULE_OFFSETS_MINUTES = {
    "on_due": 0,
    "1_day": 1 * 1440,
    "2_days": 2 * 1440,
    "3_days": 3 * 1440,
    "1_week": 7 * 1440,
    "2_weeks": 14 * 1440,
    "1_month": 30 * 1440,
}
