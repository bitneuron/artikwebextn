"""ArtikFinance Alerts — persistent store for natural-language financial alerts.

Alerts are structured rules (source + metric + filters + conditions + schedule + Slack
destination) created via the chatbot, confirmed by the user, evaluated on schedule, and
delivered through the EXISTING Artik Notifier Slack integration. Stored in the SAME SQLite
DB as users (USERS_DB_PATH) so it rides the Litestream→S3 replication and survives redeploys.

Security invariants:
- Everything is scoped by user_id — a user only ever sees/edits their own alerts.
- Only allow-listed sources/metrics/operators/frequencies are ever persisted (validation
  lives in alerts_engine); this store never executes raw expressions.
- Slack webhook URLs / signing secrets are NEVER stored here — only the destination label
  (e.g. '#artik') and delivery results.
- Soft delete (deleted_at) — alerts are never hard-deleted.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_DB_PATH = Path(os.environ.get("USERS_DB_PATH", str(_HERE / "config" / "users.db")))
_lock = threading.RLock()


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(_DB_PATH), timeout=10, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=5000")
    return c


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def init() -> None:
    with _lock, _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS financial_alerts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER,
          name TEXT NOT NULL,
          description TEXT,
          source_type TEXT NOT NULL,
          metric TEXT,
          filters_json TEXT,
          conditions_json TEXT NOT NULL,
          logical_operator TEXT DEFAULT 'AND',
          schedule_json TEXT NOT NULL,
          notification_json TEXT NOT NULL,
          trigger_mode TEXT DEFAULT 'state_change',
          cooldown_minutes INTEGER DEFAULT 1440,
          is_enabled INTEGER DEFAULT 1,
          last_state INTEGER,
          last_value_json TEXT,
          last_checked_at TEXT,
          last_triggered_at TEXT,
          next_run_at TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT,
          deleted_at TEXT);
        CREATE INDEX IF NOT EXISTS ix_alerts_user ON financial_alerts(user_id, deleted_at);
        CREATE INDEX IF NOT EXISTS ix_alerts_due ON financial_alerts(is_enabled, deleted_at, next_run_at);
        CREATE TABLE IF NOT EXISTS financial_alert_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          alert_id INTEGER NOT NULL,
          user_id INTEGER,
          started_at TEXT,
          completed_at TEXT,
          evaluated_value_json TEXT,
          condition_result INTEGER,
          previous_state INTEGER,
          current_state INTEGER,
          notification_sent INTEGER DEFAULT 0,
          notification_status TEXT,
          error_message TEXT,
          created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS ix_alertruns ON financial_alert_runs(alert_id, id DESC);
        CREATE TABLE IF NOT EXISTS financial_alert_notifications (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          alert_id INTEGER NOT NULL,
          run_id INTEGER,
          user_id INTEGER,
          channel TEXT,
          destination_type TEXT,
          destination TEXT,
          delivery_status TEXT,
          slack_message_ts TEXT,
          sent_at TEXT,
          error_message TEXT,
          created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS financial_alert_audit (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          alert_id INTEGER, user_id INTEGER, action TEXT, detail TEXT, created_at TEXT NOT NULL);
        """)


_JSON_FIELDS = {"filters_json": "filters", "conditions_json": "conditions",
                "schedule_json": "schedule", "notification_json": "notification",
                "last_value_json": "last_value"}


def _row_to_alert(r: sqlite3.Row) -> dict:
    d = dict(r)
    for col, key in _JSON_FIELDS.items():
        raw = d.pop(col, None)
        try:
            d[key] = json.loads(raw) if raw else (None if key == "last_value" else {})
        except Exception:  # noqa: BLE001
            d[key] = None if key == "last_value" else {}
    d["is_enabled"] = bool(d.get("is_enabled"))
    if d.get("last_state") is not None:
        d["last_state"] = bool(d["last_state"])
    return d


def audit(alert_id: int | None, user_id, action: str, detail: str = "") -> None:
    with _lock, _conn() as c:
        c.execute("INSERT INTO financial_alert_audit (alert_id, user_id, action, detail, created_at) "
                  "VALUES (?,?,?,?,?)", (alert_id, user_id, action, (detail or "")[:500], _now()))


# ── CRUD (all user-scoped) ────────────────────────────────────────────────────
def create(user_id, alert: dict, next_run_at: str | None) -> dict:
    init()
    now = _now()
    with _lock, _conn() as c:
        cur = c.execute(
            """INSERT INTO financial_alerts
               (user_id, name, description, source_type, metric, filters_json, conditions_json,
                logical_operator, schedule_json, notification_json, trigger_mode, cooldown_minutes,
                is_enabled, next_run_at, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (user_id, alert["name"][:200], (alert.get("description") or "")[:500],
             alert["source_type"], alert.get("metric"),
             json.dumps(alert.get("filters") or {}), json.dumps(alert.get("conditions") or []),
             (alert.get("logical_operator") or "AND"),
             json.dumps(alert["schedule"]), json.dumps(alert["notification"]),
             alert.get("trigger_mode") or "state_change",
             int(alert.get("cooldown_minutes") or 1440),
             1 if alert.get("is_enabled", True) else 0, next_run_at, now, now))
        aid = cur.lastrowid
    audit(aid, user_id, "create", alert["name"])
    return get(user_id, aid)


def get(user_id, alert_id: int, allow_deleted: bool = False) -> dict | None:
    init()
    with _conn() as c:
        q = "SELECT * FROM financial_alerts WHERE id=? AND user_id=?"
        if not allow_deleted:
            q += " AND deleted_at IS NULL"
        r = c.execute(q, (alert_id, user_id)).fetchone()
    return _row_to_alert(r) if r else None


def list_alerts(user_id, status: str | None = None) -> list[dict]:
    """status: active | paused | triggered | all (None=all non-deleted)."""
    init()
    with _conn() as c:
        rows = [_row_to_alert(r) for r in c.execute(
            "SELECT * FROM financial_alerts WHERE user_id=? AND deleted_at IS NULL "
            "ORDER BY created_at DESC", (user_id,)).fetchall()]
    if status == "active":
        rows = [a for a in rows if a["is_enabled"]]
    elif status == "paused":
        rows = [a for a in rows if not a["is_enabled"]]
    elif status == "triggered":
        rows = [a for a in rows if a.get("last_state")]
    return rows


_UPDATABLE = {"name", "description", "source_type", "metric", "filters", "conditions",
              "logical_operator", "schedule", "notification", "trigger_mode",
              "cooldown_minutes", "is_enabled"}


def update(user_id, alert_id: int, changes: dict, next_run_at: str | None = "keep") -> dict | None:
    if not get(user_id, alert_id):
        return None
    sets, args = [], []
    for k, v in changes.items():
        if k not in _UPDATABLE:
            continue
        col = {"filters": "filters_json", "conditions": "conditions_json",
               "schedule": "schedule_json", "notification": "notification_json"}.get(k, k)
        if k in ("filters", "conditions", "schedule", "notification"):
            v = json.dumps(v)
        elif k == "is_enabled":
            v = 1 if v else 0
        elif k == "name":
            v = str(v)[:200]
        elif k == "description":
            v = str(v)[:500]
        sets.append(f"{col}=?")
        args.append(v)
    if next_run_at != "keep":
        sets.append("next_run_at=?")
        args.append(next_run_at)
    sets.append("updated_at=?")
    args.append(_now())
    with _lock, _conn() as c:
        c.execute(f"UPDATE financial_alerts SET {', '.join(sets)} WHERE id=? AND user_id=?",
                  args + [alert_id, user_id])
    audit(alert_id, user_id, "update", ",".join(changes))
    return get(user_id, alert_id)


def set_enabled(user_id, alert_id: int, enabled: bool, next_run_at: str | None) -> dict | None:
    a = update(user_id, alert_id, {"is_enabled": enabled}, next_run_at=next_run_at)
    if a:
        audit(alert_id, user_id, "resume" if enabled else "pause", "")
    return a


def soft_delete(user_id, alert_id: int) -> bool:
    if not get(user_id, alert_id):
        return False
    with _lock, _conn() as c:
        c.execute("UPDATE financial_alerts SET deleted_at=?, is_enabled=0 WHERE id=? AND user_id=?",
                  (_now(), alert_id, user_id))
    audit(alert_id, user_id, "delete", "")
    return True


def record_evaluation(user_id, alert_id: int, *, state: bool, value, next_run_at: str | None,
                      triggered: bool) -> None:
    """Persist the post-run alert state (last_state/value/checked/triggered/next_run)."""
    with _lock, _conn() as c:
        c.execute("UPDATE financial_alerts SET last_state=?, last_value_json=?, last_checked_at=?, "
                  + ("last_triggered_at=?, " if triggered else "")
                  + "next_run_at=? WHERE id=? AND user_id=?",
                  ([1 if state else 0, json.dumps(value), _now()]
                   + ([_now()] if triggered else []) + [next_run_at, alert_id, user_id]))


# ── run + notification history ────────────────────────────────────────────────
def create_run(alert_id: int, user_id) -> int:
    init()
    with _lock, _conn() as c:
        cur = c.execute("INSERT INTO financial_alert_runs (alert_id, user_id, started_at, created_at) "
                        "VALUES (?,?,?,?)", (alert_id, user_id, _now(), _now()))
        return cur.lastrowid


def finish_run(run_id: int, *, evaluated_value, condition_result: bool, previous_state,
               current_state: bool, notification_sent: bool, notification_status: str | None,
               error_message: str | None = None) -> None:
    with _lock, _conn() as c:
        c.execute("""UPDATE financial_alert_runs SET completed_at=?, evaluated_value_json=?,
                     condition_result=?, previous_state=?, current_state=?, notification_sent=?,
                     notification_status=?, error_message=? WHERE id=?""",
                  (_now(), json.dumps(evaluated_value), 1 if condition_result else 0,
                   (None if previous_state is None else (1 if previous_state else 0)),
                   1 if current_state else 0, 1 if notification_sent else 0,
                   notification_status, (error_message or None), run_id))


def record_notification(alert_id: int, run_id: int | None, user_id, *, channel: str,
                        destination_type: str, destination: str, delivery_status: str,
                        slack_message_ts: str | None = None, error_message: str | None = None) -> None:
    with _lock, _conn() as c:
        c.execute("""INSERT INTO financial_alert_notifications
                     (alert_id, run_id, user_id, channel, destination_type, destination,
                      delivery_status, slack_message_ts, sent_at, error_message, created_at)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                  (alert_id, run_id, user_id, channel, destination_type, destination,
                   delivery_status, slack_message_ts,
                   (_now() if delivery_status == "sent" else None), error_message, _now()))


def history(user_id, alert_id: int, limit: int = 50) -> dict:
    """Runs + notifications for one alert (ownership-checked by caller via get())."""
    with _conn() as c:
        runs = [dict(r) for r in c.execute(
            "SELECT * FROM financial_alert_runs WHERE alert_id=? AND user_id=? "
            "ORDER BY id DESC LIMIT ?", (alert_id, user_id, limit)).fetchall()]
        notes = [dict(r) for r in c.execute(
            "SELECT * FROM financial_alert_notifications WHERE alert_id=? AND user_id=? "
            "ORDER BY id DESC LIMIT ?", (alert_id, user_id, limit)).fetchall()]
    for r in runs:
        try:
            r["evaluated_value"] = json.loads(r.pop("evaluated_value_json") or "null")
        except Exception:  # noqa: BLE001
            r["evaluated_value"] = None
    return {"runs": runs, "notifications": notes}


def due_alerts(now_iso: str) -> list[dict]:
    """Enabled, non-deleted alerts whose next_run_at has passed — for the scheduler tick."""
    init()
    with _conn() as c:
        rows = [_row_to_alert(r) for r in c.execute(
            "SELECT * FROM financial_alerts WHERE is_enabled=1 AND deleted_at IS NULL "
            "AND (next_run_at IS NULL OR next_run_at<=?) ORDER BY next_run_at", (now_iso,)).fetchall()]
    return rows


def name_exists(user_id, name: str, exclude_id: int | None = None) -> bool:
    with _conn() as c:
        r = c.execute("SELECT id FROM financial_alerts WHERE user_id=? AND deleted_at IS NULL "
                      "AND LOWER(name)=LOWER(?)", (user_id, (name or "").strip())).fetchall()
    return any(row["id"] != exclude_id for row in r)
