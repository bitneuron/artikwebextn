"""Persistent intelligence snapshots (for Today / 7-day / 30-day / 90-day trends).

Stored in the SAME SQLite DB as users (USERS_DB_PATH) so they ride the Litestream→S3
replication. One row per (ticker, day): the composite score/label + the full signals JSON.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("USERS_DB_PATH", str(_HERE / "config" / "users.db")))
_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH), timeout=10, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=5000")
    return c


def init() -> None:
    with _lock, _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS intelligence_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                day TEXT NOT NULL,
                composite_score REAL,
                composite_label TEXT,
                confidence REAL,
                signals TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(ticker, day)
            )""")


def save(ticker: str, signals: dict) -> None:
    """Upsert one snapshot per ticker per day (latest wins)."""
    init()
    comp = signals.get("composite") or {}
    now = datetime.now(timezone.utc)
    with _lock, _conn() as c:
        c.execute("""
            INSERT INTO intelligence_snapshots (ticker, day, composite_score, composite_label, confidence, signals, created_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(ticker, day) DO UPDATE SET
                composite_score=excluded.composite_score, composite_label=excluded.composite_label,
                confidence=excluded.confidence, signals=excluded.signals, created_at=excluded.created_at
            """, (ticker.upper(), date.today().isoformat(), comp.get("score"), comp.get("signal"),
                  comp.get("confidence"), json.dumps(signals), now.strftime("%Y-%m-%dT%H:%M:%SZ")))


def trend(ticker: str, days: int = 90) -> list[dict]:
    """Composite score/label per day over the window (oldest → newest)."""
    init()
    since = (date.today() - timedelta(days=days)).isoformat()
    with _conn() as c:
        rows = c.execute(
            "SELECT day, composite_score, composite_label, confidence FROM intelligence_snapshots "
            "WHERE ticker=? AND day>=? ORDER BY day ASC", (ticker.upper(), since)).fetchall()
    return [dict(r) for r in rows]
