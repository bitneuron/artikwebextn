"""Persistent store for E*TRADE-sourced portfolio snapshots.

Stored in the SAME SQLite DB as users (USERS_DB_PATH) so they're covered by the
Litestream→S3 replication and survive redeploys. NEVER stores E*TRADE tokens or
credentials — only holdings (ticker/qty/cost_basis), totals, and metadata.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
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
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                source TEXT NOT NULL,            -- 'etrade'
                label TEXT,
                account_ending TEXT,
                holdings TEXT NOT NULL,          -- JSON [{ticker,qty,cost_basis}]
                total_value REAL,
                total_gain REAL,
                created_at TEXT NOT NULL
            )""")


def create(*, user_id: int | None, source: str, label: str, account_ending: str,
           holdings: list, total_value: float | None, total_gain: float | None) -> int:
    init()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _lock, _conn() as c:
        cur = c.execute(
            """INSERT INTO portfolio_snapshots
               (user_id, source, label, account_ending, holdings, total_value, total_gain, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (user_id, source, label, account_ending, json.dumps(holdings),
             total_value, total_gain, now))
        return int(cur.lastrowid)


def list_snapshots(source: str | None = None) -> list[dict]:
    init()
    q = ("SELECT id, source, label, account_ending, total_value, total_gain, created_at "
         "FROM portfolio_snapshots")
    vals: list = []
    if source:
        q += " WHERE source=?"
        vals.append(source)
    q += " ORDER BY id DESC"
    with _conn() as c:
        return [dict(r) for r in c.execute(q, vals).fetchall()]


def get(snapshot_id: int) -> dict | None:
    init()
    with _conn() as c:
        r = c.execute("SELECT * FROM portfolio_snapshots WHERE id=?", (snapshot_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["holdings"] = json.loads(d["holdings"] or "[]")
    return d
