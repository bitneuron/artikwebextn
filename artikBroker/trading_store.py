"""Durable KV store for the Autonomous Trading Desk.

Reuses the same `app_kv` table in the users DB (USERS_DB_PATH) that agents_store uses, so
settings / paper trades / decision log survive App Runner redeploys via Litestream→S3. All values
are namespaced under `trading:*` keys. No portfolio holdings are stored here — the Portfolio page
remains the single source of truth; only trading settings, paper positions, and logs live here.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_DB_PATH = Path(os.environ.get("USERS_DB_PATH", str(_HERE / "config" / "users.db")))
_lock = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(_DB_PATH), timeout=10, check_same_thread=False)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=5000")
    c.execute("CREATE TABLE IF NOT EXISTS app_kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    return c


def kv_get(key: str, default=None):
    try:
        with _conn() as c:
            row = c.execute("SELECT value FROM app_kv WHERE key=?", (f"trading:{key}",)).fetchone()
        return json.loads(row[0]) if row else default
    except Exception:  # noqa: BLE001
        return default


def kv_set(key: str, value) -> bool:
    try:
        with _conn() as c:
            c.execute("INSERT INTO app_kv (key, value) VALUES (?,?) "
                      "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                      (f"trading:{key}", json.dumps(value)))
        return True
    except Exception:  # noqa: BLE001
        return False


# ── settings (single shared config; live-trading fields are admin-gated at the API layer) ──
def get_settings() -> dict:
    from trading_desk import DEFAULT_SETTINGS
    saved = kv_get("settings") or {}
    return {**DEFAULT_SETTINGS, **saved}


def save_settings(patch: dict) -> dict:
    with _lock:
        cur = get_settings()
        cur.update(patch or {})
        kv_set("settings", cur)
        return cur


# ── runtime state (pause / kill switch / counters) ──
def get_state() -> dict:
    st = kv_get("state") or {}
    return {"paused": False, "killed": False, "last_scan": None,
            "trades_today": 0, "trades_day": None, **st}


def set_state(patch: dict) -> dict:
    with _lock:
        st = get_state()
        st.update(patch or {})
        kv_set("state", st)
        return st


# ── paper trading positions ──
def list_paper(status: str | None = None) -> list[dict]:
    rows = kv_get("paper", []) or []
    return [r for r in rows if not status or r.get("status") == status]


def add_paper(pos: dict) -> dict:
    with _lock:
        rows = kv_get("paper", []) or []
        pos = {"id": uuid.uuid4().hex[:12], "status": "open", "opened_at": _now(),
               "realized_pl": None, "closed_at": None, **pos}
        rows.append(pos)
        kv_set("paper", rows)
        return pos


def update_paper(pos_id: str, patch: dict) -> dict | None:
    with _lock:
        rows = kv_get("paper", []) or []
        for r in rows:
            if r.get("id") == pos_id:
                r.update(patch or {})
                kv_set("paper", rows)
                return r
        return None


def close_paper(pos_id: str, exit_price: float) -> dict | None:
    with _lock:
        rows = kv_get("paper", []) or []
        for r in rows:
            if r.get("id") == pos_id and r.get("status") == "open":
                qty = float(r.get("qty") or 0)
                entry = float(r.get("entry") or 0)
                side = r.get("side", "BUY")
                pl = (exit_price - entry) * qty if side == "BUY" else (entry - exit_price) * qty
                r.update(status="closed", exit=exit_price, realized_pl=round(pl, 2), closed_at=_now())
                kv_set("paper", rows)
                return r
        return None


# ── live order queue (Phase 2: approval → Mac execution bridge) ──
# statuses: pending_approval → approved → submitted → filled | failed | cancelled | rejected
def list_orders(status: str | None = None, limit: int = 100) -> list[dict]:
    rows = kv_get("orders", []) or []
    if status:
        rows = [r for r in rows if r.get("status") == status]
    return rows[:limit]


def get_order(order_id: str) -> dict | None:
    return next((r for r in (kv_get("orders", []) or []) if r.get("id") == order_id), None)


def add_order(order: dict) -> dict:
    with _lock:
        rows = kv_get("orders", []) or []
        order = {"id": uuid.uuid4().hex[:12], "ts": _now(), "status": "pending_approval",
                 "order_type": "MKT", "tif": "DAY", "sec_type": "STK", "result": None, **order}
        rows.insert(0, order)
        kv_set("orders", rows[:300])
        return order


def update_order(order_id: str, patch: dict) -> dict | None:
    with _lock:
        rows = kv_get("orders", []) or []
        for r in rows:
            if r.get("id") == order_id:
                r.update(patch or {})
                r["updated_at"] = _now()
                kv_set("orders", rows)
                return r
        return None


def rollover_day() -> dict:
    """Reset trades_today when the (UTC) day changes. Called by the scheduler each tick."""
    with _lock:
        st = get_state()
        today = _now()[:10]
        if st.get("trades_day") != today:
            st.update(trades_day=today, trades_today=0)
            kv_set("state", st)
        return st


# ── decision log (bounded ring) ──
def log_decision(entry: dict) -> None:
    with _lock:
        rows = kv_get("log", []) or []
        rows.insert(0, {"ts": _now(), **entry})
        kv_set("log", rows[:200])


def list_log(limit: int = 50) -> list[dict]:
    return (kv_get("log", []) or [])[:limit]
