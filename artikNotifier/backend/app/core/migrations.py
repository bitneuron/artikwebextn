"""Idempotent, code-based migrations for the notes-first redesign.

`create_all()` adds NEW tables (notebooks) but never ALTERs existing ones, so the new
quick_notes columns are added here. Also seeds a default notebook per user, backfills every
note into a notebook, and migrates existing Reminder records into linked Notes (once) so the
app is notes-first without losing any data. Safe to run on every startup.
"""
from __future__ import annotations

from sqlalchemy import inspect, text

from app.core.database import SessionLocal, engine
from app.core.logging_config import log_event

_QN_COLUMNS = {
    "notebook_id": "INTEGER",
    "is_favorite": "BOOLEAN DEFAULT 0",
    "pinned": "BOOLEAN DEFAULT 0",
    "repeat": "VARCHAR(16)",
}


def run_migrations() -> None:
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    if "quick_notes" in tables:
        existing = {c["name"] for c in insp.get_columns("quick_notes")}
        with engine.begin() as conn:
            for col, ddl in _QN_COLUMNS.items():
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE quick_notes ADD COLUMN {col} {ddl}"))
                    log_event("migration", "add_column", table="quick_notes", column=col)
    try:
        _seed_and_backfill()
    except Exception as e:  # noqa: BLE001 — never block startup on data migration
        log_event("migration", "seed_error", error=str(e))


def _seed_and_backfill() -> None:
    from app.models.notebook import Notebook
    from app.models.quick_note import QuickNote
    from app.models.reminder import Reminder
    from app.models.user import User

    db = SessionLocal()
    try:
        for u in db.query(User).all():
            default = (db.query(Notebook)
                       .filter(Notebook.user_id == u.id, Notebook.is_default.is_(True)).first())
            if not default:
                default = Notebook(user_id=u.id, name="Personal", icon="📓", is_default=True)
                db.add(default)
                db.flush()
            # Every existing note must belong to a notebook.
            (db.query(QuickNote)
               .filter(QuickNote.user_id == u.id, QuickNote.notebook_id.is_(None))
               .update({QuickNote.notebook_id: default.id}, synchronize_session=False))

            # Migrate reminders → linked notes (once each), into a "Reminders" notebook.
            linked = {qn.reminder_id for qn in db.query(QuickNote)
                      .filter(QuickNote.user_id == u.id, QuickNote.reminder_id.isnot(None)).all()}
            reminders = db.query(Reminder).filter(Reminder.user_id == u.id).all()
            rnb = None
            for r in reminders:
                if r.id in linked:
                    continue
                if rnb is None:
                    rnb = (db.query(Notebook)
                           .filter(Notebook.user_id == u.id, Notebook.name == "Reminders").first())
                    if rnb is None:
                        rnb = Notebook(user_id=u.id, name="Reminders", icon="⏰")
                        db.add(rnb)
                        db.flush()
                due = r.due_at
                db.add(QuickNote(
                    user_id=u.id, notebook_id=rnb.id, title=r.title,
                    note_text=(r.description or r.notes or r.title or "Reminder"),
                    category=r.category or "Personal", priority=r.priority or "medium",
                    status="active",
                    due_date=(due.date() if due else None),
                    due_time=(f"{due.hour:02d}:{due.minute:02d}" if due else None),
                    repeat=(r.recurrence if r.recurrence and r.recurrence != "one_time" else None),
                    reminder_id=r.id))
        db.commit()
    finally:
        db.close()
