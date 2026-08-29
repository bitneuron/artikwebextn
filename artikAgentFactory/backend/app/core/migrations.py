"""Idempotent, code-based startup migrations.

`init_db()`'s `create_all()` covers brand-new tables; this file adds columns to
tables that pre-date a schema change (matching artikNotifier's `core/migrations.py`
pattern). Safe to run on every startup.
"""
from __future__ import annotations

from sqlalchemy import inspect, text

from app.core.database import SessionLocal, engine
from app.core.logging_config import log_event

_AGENT_COLUMNS = {
    "owner_id": "INTEGER",
    "workspace_id": "INTEGER",
    "visibility": "VARCHAR(16) DEFAULT 'private'",
}


def run_migrations() -> None:
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    if "agents" in tables:
        existing = {c["name"] for c in insp.get_columns("agents")}
        with engine.begin() as conn:
            for col, ddl in _AGENT_COLUMNS.items():
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE agents ADD COLUMN {col} {ddl}"))
                    log_event("migration", "add_column", table="agents", column=col)

    _ensure_default_workspace()


def _ensure_default_workspace() -> None:
    from app.models.workspace import Workspace

    db = SessionLocal()
    try:
        if not db.query(Workspace).first():
            db.add(Workspace(name="Default", slug="default"))
            db.commit()
            log_event("migration", "created default workspace")
    finally:
        db.close()


def backfill_legacy_agents(admin_user_id: int, workspace_id: int) -> None:
    """Assign a real owner/workspace to any agent rows created before auth existed.
    Called once, right after the first-admin bootstrap (needs a real user id to
    backfill onto) — see auth/bootstrap.py."""
    from app.models.agent import Agent

    db = SessionLocal()
    try:
        orphans = db.query(Agent).filter(Agent.owner_id.is_(None)).all()
        if not orphans:
            return
        for a in orphans:
            a.owner_id = admin_user_id
            a.workspace_id = workspace_id
            a.visibility = a.visibility or "private"
        db.commit()
        log_event("migration", "backfilled legacy agents", count=len(orphans))
    finally:
        db.close()
