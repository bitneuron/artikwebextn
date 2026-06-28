"""Small pure helpers: JSON-list (de)serialization and recurrence math."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone


def ensure_aware(dt: datetime | None) -> datetime | None:
    """SQLite drops tzinfo on read — coerce naive datetimes back to UTC-aware so
    comparisons with timezone-aware `now()` don't raise."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def to_json_list(values) -> str:
    out = []
    for v in (values or []):
        out.append(v.value if hasattr(v, "value") else str(v))
    return json.dumps(out)


def from_json_list(text: str | None) -> list[str]:
    if not text:
        return []
    try:
        data = json.loads(text)
        return [str(x) for x in data] if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def add_months(dt: datetime, months: int) -> datetime:
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    # clamp day to end of target month
    day = min(dt.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                       31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return dt.replace(year=year, month=month, day=day)


def next_occurrence(due_at: datetime, recurrence: str) -> datetime | None:
    """The next due date for a recurring reminder, or None for one_time."""
    if recurrence == "daily":
        return due_at + timedelta(days=1)
    if recurrence == "weekly":
        return due_at + timedelta(weeks=1)
    if recurrence == "monthly":
        return add_months(due_at, 1)
    if recurrence == "quarterly":
        return add_months(due_at, 3)
    if recurrence == "yearly":
        return add_months(due_at, 12)
    return None
