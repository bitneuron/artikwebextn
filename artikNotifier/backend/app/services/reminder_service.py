"""Reminder business logic: CRUD + lifecycle (complete/archive/snooze/duplicate/
restore) + (re)building the notification_rules that the scheduler fires from."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.utils import from_json_list, next_occurrence, to_json_list
from app.models.enums import SCHEDULE_OFFSETS_MINUTES
from app.models.reminder import Reminder, ReminderHistory
from app.models.notification import NotificationRule
from app.repositories.notification_repo import NotificationRuleRepository
from app.repositories.reminder_repo import ReminderRepository


class ReminderNotFound(Exception):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class ReminderService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ReminderRepository(db)
        self.rules = NotificationRuleRepository(db)

    # ── serialization ─────────────────────────────────────────────────────────
    def to_out(self, r: Reminder) -> dict:
        return {
            "id": r.id, "user_id": r.user_id, "title": r.title,
            "description": r.description, "notes": r.notes, "category": r.category,
            "priority": r.priority, "status": r.status, "due_at": r.due_at,
            "timezone": r.timezone, "recurrence": r.recurrence,
            "schedule": from_json_list(r.schedule), "channels": from_json_list(r.channels),
            "tags": [t.name for t in r.tags],
            "completed_at": r.completed_at, "snoozed_until": r.snoozed_until,
            "created_at": r.created_at, "updated_at": r.updated_at,
        }

    def _history(self, r: Reminder, action: str, detail: str | None = None) -> None:
        self.db.add(ReminderHistory(reminder_id=r.id, user_id=r.user_id, action=action, detail=detail))

    # ── notification-rule (re)build ──────────────────────────────────────────
    def rebuild_rules(self, r: Reminder) -> None:
        """Drop unfired rules + recreate from the reminder's schedule offsets. Past
        fire-times are skipped (we never spam history); idempotent via dedupe_key."""
        self.rules.delete_for_reminder(r.id, only_unfired=True)
        if r.status not in ("active", "snoozed"):
            return
        due = _ensure_aware(r.due_at)
        channels = r.channels
        for offset in from_json_list(r.schedule):
            mins = SCHEDULE_OFFSETS_MINUTES.get(offset)
            if mins is None:
                continue
            fire_at = due - timedelta(minutes=mins)
            dedupe = f"r{r.id}:{offset}:{int(due.timestamp())}"
            if self.rules.get_by_dedupe(dedupe):
                continue
            self.db.add(NotificationRule(
                reminder_id=r.id, user_id=r.user_id, offset_key=offset,
                fire_at=fire_at, channels=channels, dedupe_key=dedupe))
        self.db.flush()

    # ── CRUD ──────────────────────────────────────────────────────────────────
    def create(self, user_id: int, data) -> Reminder:
        r = Reminder(
            user_id=user_id, title=data.title, description=data.description, notes=data.notes,
            category=data.category, priority=data.priority.value, due_at=_ensure_aware(data.due_at),
            timezone=data.timezone, recurrence=data.recurrence.value,
            schedule=to_json_list(data.schedule), channels=to_json_list(data.channels), status="active")
        self.repo.add(r)
        for name in data.tags:
            r.tags.append(self.repo.get_or_create_tag(user_id, name))
        self._history(r, "created")
        self.rebuild_rules(r)
        self.db.commit()
        self.db.refresh(r)
        return r

    def get(self, user_id: int, reminder_id: int) -> Reminder:
        r = self.repo.get_for_user(reminder_id, user_id)
        if not r or r.status == "deleted":
            raise ReminderNotFound()
        return r

    def list(self, user_id: int, **kw) -> list[Reminder]:
        return self.repo.query(user_id, **kw)

    def update(self, user_id: int, reminder_id: int, data) -> Reminder:
        r = self.get(user_id, reminder_id)
        fields = data.model_dump(exclude_unset=True)
        for f in ("title", "description", "notes", "category", "timezone"):
            if f in fields:
                setattr(r, f, fields[f])
        if "priority" in fields and fields["priority"]:
            r.priority = fields["priority"].value if hasattr(fields["priority"], "value") else fields["priority"]
        if "recurrence" in fields and fields["recurrence"]:
            r.recurrence = fields["recurrence"].value if hasattr(fields["recurrence"], "value") else fields["recurrence"]
        if "status" in fields and fields["status"]:
            r.status = fields["status"].value if hasattr(fields["status"], "value") else fields["status"]
        if "due_at" in fields and fields["due_at"]:
            r.due_at = _ensure_aware(fields["due_at"])
        if "schedule" in fields and fields["schedule"] is not None:
            r.schedule = to_json_list(fields["schedule"])
        if "channels" in fields and fields["channels"] is not None:
            r.channels = to_json_list(fields["channels"])
        if "tags" in fields and fields["tags"] is not None:
            r.tags = [self.repo.get_or_create_tag(user_id, n) for n in fields["tags"]]
        self._history(r, "updated")
        self.rebuild_rules(r)
        self.db.commit()
        self.db.refresh(r)
        return r

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def complete(self, user_id: int, reminder_id: int) -> Reminder:
        r = self.get(user_id, reminder_id)
        nxt = next_occurrence(_ensure_aware(r.due_at), r.recurrence)
        r.completed_at = _utcnow()
        if nxt:
            # recurring → roll forward to the next occurrence, stay active
            self._history(r, "completed_occurrence", f"next={nxt.isoformat()}")
            r.due_at, r.status, r.completed_at, r.snoozed_until = nxt, "active", None, None
            self.rebuild_rules(r)
        else:
            r.status = "completed"
            self.rules.delete_for_reminder(r.id, only_unfired=True)
            self._history(r, "completed")
        self.db.commit()
        self.db.refresh(r)
        return r

    def archive(self, user_id: int, reminder_id: int) -> Reminder:
        r = self.get(user_id, reminder_id)
        r.status = "archived"
        self.rules.delete_for_reminder(r.id, only_unfired=True)
        self._history(r, "archived")
        self.db.commit(); self.db.refresh(r)
        return r

    def restore(self, user_id: int, reminder_id: int) -> Reminder:
        r = self.repo.get_for_user(reminder_id, user_id)
        if not r:
            raise ReminderNotFound()
        r.status = "active"
        r.completed_at = r.snoozed_until = None
        self._history(r, "restored")
        self.rebuild_rules(r)
        self.db.commit(); self.db.refresh(r)
        return r

    def snooze(self, user_id: int, reminder_id: int, *, minutes: int | None, until: datetime | None) -> Reminder:
        r = self.get(user_id, reminder_id)
        target = _ensure_aware(until) if until else _utcnow() + timedelta(minutes=minutes or 60)
        r.snoozed_until = target
        r.due_at = target
        r.status = "snoozed"
        self._history(r, "snoozed", f"until={target.isoformat()}")
        self.rebuild_rules(r)
        self.db.commit(); self.db.refresh(r)
        return r

    def duplicate(self, user_id: int, reminder_id: int) -> Reminder:
        r = self.get(user_id, reminder_id)
        copy = Reminder(
            user_id=user_id, title=f"{r.title} (copy)", description=r.description, notes=r.notes,
            category=r.category, priority=r.priority, due_at=r.due_at, timezone=r.timezone,
            recurrence=r.recurrence, schedule=r.schedule, channels=r.channels, status="active")
        self.repo.add(copy)
        copy.tags = list(r.tags)
        self._history(copy, "duplicated", f"from={r.id}")
        self.rebuild_rules(copy)
        self.db.commit(); self.db.refresh(copy)
        return copy

    def delete(self, user_id: int, reminder_id: int) -> None:
        r = self.repo.get_for_user(reminder_id, user_id)
        if not r:
            raise ReminderNotFound()
        r.status = "deleted"
        self.rules.delete_for_reminder(r.id, only_unfired=True)
        self._history(r, "deleted")
        self.db.commit()
