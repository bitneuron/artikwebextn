"""Quick Notes business logic: CRUD + lifecycle (complete/archive/restore/delete) +
one-click conversion into a full Reminder. Every mutating action is audit-logged.

All access goes through `repo.get_for_user(id, user_id)` so a user can only ever touch
their own notes (IDOR-safe), mirroring the Reminder module's security model.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.logging_config import log_event
from app.models.enums import Priority, Recurrence
from app.models.quick_note import QuickNote
from app.models.system import AuditLog
from app.repositories.quick_note_repo import QuickNoteRepository
from app.schemas.reminder import ReminderCreate
from app.services.reminder_service import ReminderService


class QuickNoteNotFound(Exception):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QuickNoteService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = QuickNoteRepository(db)

    # ── serialization / audit ─────────────────────────────────────────────────
    def to_out(self, n: QuickNote) -> dict:
        return {
            "id": n.id, "user_id": n.user_id, "title": n.title, "note_text": n.note_text,
            "category": n.category, "priority": n.priority, "status": n.status,
            "due_date": n.due_date, "due_time": n.due_time, "reminder_id": n.reminder_id,
            "archived": n.archived, "deleted": n.deleted,
            "tags": [t.name for t in n.tags],
            "created_at": n.created_at, "updated_at": n.updated_at,
        }

    def _audit(self, user_id: int, action: str, note_id: int | None, detail: str = "") -> None:
        self.db.add(AuditLog(user_id=user_id, action=action, entity="quick_note",
                             entity_id=note_id, detail=detail))
        log_event("audit", action, actor=user_id, entity_id=note_id, detail=detail)

    # ── CRUD ──────────────────────────────────────────────────────────────────
    def create(self, user_id: int, data) -> QuickNote:
        n = QuickNote(
            user_id=user_id, title=data.title, note_text=data.note_text,
            category=data.category, priority=data.priority.value,
            due_date=data.due_date, due_time=data.due_time, status="active")
        self.repo.add(n)
        for name in data.tags:
            if name and name.strip():
                n.tags.append(self.repo.get_or_create_tag(user_id, name))
        self._audit(user_id, "note.create", n.id, (data.title or data.note_text)[:80])
        self.db.commit()
        self.db.refresh(n)
        return n

    def get(self, user_id: int, note_id: int) -> QuickNote:
        n = self.repo.get_for_user(note_id, user_id)
        if not n or n.status == "deleted":
            raise QuickNoteNotFound()
        return n

    def list(self, user_id: int, **kw) -> list[QuickNote]:
        return self.repo.query(user_id, **kw)

    def update(self, user_id: int, note_id: int, data) -> QuickNote:
        n = self.get(user_id, note_id)
        fields = data.model_dump(exclude_unset=True)
        for f in ("title", "note_text", "category", "due_date", "due_time"):
            if f in fields:
                setattr(n, f, fields[f])
        if fields.get("priority"):
            n.priority = getattr(fields["priority"], "value", fields["priority"])
        if fields.get("status"):
            self._apply_status(n, getattr(fields["status"], "value", fields["status"]))
        if "tags" in fields and fields["tags"] is not None:
            n.tags = [self.repo.get_or_create_tag(user_id, t) for t in fields["tags"] if t and t.strip()]
        self._audit(user_id, "note.update", n.id)
        self.db.commit()
        self.db.refresh(n)
        return n

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def _apply_status(self, n: QuickNote, status: str) -> None:
        n.status = status
        n.archived = status == "archived"
        n.deleted = status == "deleted"

    def complete(self, user_id: int, note_id: int) -> QuickNote:
        n = self.get(user_id, note_id)
        self._apply_status(n, "completed")
        self._audit(user_id, "note.complete", n.id)
        self.db.commit(); self.db.refresh(n)
        return n

    def archive(self, user_id: int, note_id: int) -> QuickNote:
        n = self.get(user_id, note_id)
        self._apply_status(n, "archived")
        self._audit(user_id, "note.archive", n.id)
        self.db.commit(); self.db.refresh(n)
        return n

    def restore(self, user_id: int, note_id: int) -> QuickNote:
        n = self.repo.get_for_user(note_id, user_id)
        if not n:
            raise QuickNoteNotFound()
        self._apply_status(n, "active")
        self._audit(user_id, "note.restore", n.id)
        self.db.commit(); self.db.refresh(n)
        return n

    def delete(self, user_id: int, note_id: int) -> None:
        n = self.repo.get_for_user(note_id, user_id)
        if not n:
            raise QuickNoteNotFound()
        self._apply_status(n, "deleted")          # soft delete (recoverable)
        self._audit(user_id, "note.delete", n.id)
        self.db.commit()

    # ── conversion ────────────────────────────────────────────────────────────
    def _due_at(self, n: QuickNote) -> datetime:
        """Combine note due_date/due_time into an aware datetime for the reminder.
        Falls back to tomorrow 09:00 UTC when the note has no due date."""
        if n.due_date:
            hh, mm = (int(x) for x in n.due_time.split(":")) if n.due_time else (9, 0)
            return datetime.combine(n.due_date, time(hh, mm), tzinfo=timezone.utc)
        return (_utcnow() + timedelta(days=1)).replace(
            hour=9, minute=0, second=0, microsecond=0)

    def convert_to_reminder(self, user_id: int, note_id: int) -> tuple[QuickNote, int]:
        n = self.get(user_id, note_id)
        if n.reminder_id:
            # idempotent-ish: already linked → return existing
            return n, n.reminder_id
        payload = ReminderCreate(
            title=(n.title or n.note_text)[:255],
            description=None,
            notes=n.note_text,
            category=n.category,
            priority=Priority(n.priority),
            due_at=self._due_at(n),
            recurrence=Recurrence.one_time,
            schedule=["on_due"],
            tags=[t.name for t in n.tags],
        )
        reminder = ReminderService(self.db).create(user_id, payload)
        n.reminder_id = reminder.id          # link back; the note is preserved
        self._audit(user_id, "note.convert", n.id, f"reminder={reminder.id}")
        self.db.commit(); self.db.refresh(n)
        return n, reminder.id
