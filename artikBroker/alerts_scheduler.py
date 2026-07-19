"""ArtikFinance Alerts scheduler — a daemon thread that evaluates due alerts.

Mirrors the existing trading_scheduler pattern (in-process daemon thread; no new framework):
every tick it loads alerts whose next_run_at has passed, evaluates each against live
ArtikFinance data, applies state-change/cooldown rules, sends Slack via the existing Notifier,
records a run + notification row, and reschedules next_run_at.

`run_alert()` is the single evaluation path shared by the scheduler AND the manual "Run Now"
API, so scheduled and manual runs behave identically.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone

import alerts_engine as engine
import alerts_store as store

log = logging.getLogger("alerts.scheduler")

_TICK_SECONDS = 60
_started = False
# Per-alert Slack rate limit: at most one delivery per this many seconds.
_MIN_NOTIFY_GAP = 60
_last_notify: dict = {}


def _base_url() -> str:
    return (os.environ.get("ARTIK_BROKER_BASE_URL") or "").strip()


def _send_slack(alert: dict, title: str, body: str, severity: str) -> tuple[bool, str]:
    try:
        from notifications import notify_slack_message
    except Exception as e:  # noqa: BLE001
        return False, f"notifier unavailable: {e}"
    now = time.time()
    aid = alert.get("id")
    if aid is not None and now - _last_notify.get(aid, 0) < _MIN_NOTIFY_GAP:
        return False, "rate-limited (per-alert)"
    dest = (alert.get("notification") or {}).get("destination") or ""
    ok, detail = notify_slack_message(
        title=title, message=body, severity=severity, event_type="financial_alert",
        channel=dest or None,
        metadata={"alert_id": aid, "destination": dest,
                  "destination_type": (alert.get("notification") or {}).get("destination_type")})
    if ok and aid is not None:
        _last_notify[aid] = now
    return ok, detail


def run_alert(alert: dict, *, manual: bool = False) -> dict:
    """Evaluate ONE alert, decide + send Slack, persist run/notification, reschedule.
    Returns a summary dict. Never raises (records errors into run history)."""
    user_id = alert.get("user_id")
    aid = alert["id"]
    run_id = store.create_run(aid, user_id)
    prev_state = alert.get("last_state")
    schedule = alert.get("schedule") or {}
    next_run = engine.compute_next_run(schedule) if not manual else alert.get("next_run_at")
    notif_sent, notif_status, err = False, None, None
    try:
        result = engine.evaluate(alert)
        state = result["state"]
        will_notify = engine.should_notify(
            alert, state, prev_state, alert.get("last_triggered_at"))
        if will_notify:
            title, body, sev = engine.slack_message(alert, result, _base_url())
            notif = alert.get("notification") or {}
            ok, detail = _send_slack(alert, title, body, sev)
            notif_sent = ok
            notif_status = "sent" if ok else f"failed: {detail}"
            store.record_notification(
                aid, run_id, user_id, channel="slack",
                destination_type=notif.get("destination_type") or "default",
                destination=notif.get("destination") or "",
                delivery_status="sent" if ok else "failed",
                error_message=None if ok else detail[:300])
        triggered = notif_sent
        store.finish_run(run_id, evaluated_value=result.get("value"), condition_result=state,
                         previous_state=prev_state, current_state=state,
                         notification_sent=notif_sent, notification_status=notif_status)
        store.record_evaluation(user_id, aid, state=state, value=result.get("value"),
                                next_run_at=next_run, triggered=triggered)
        return {"ok": True, "state": state, "notified": notif_sent, "value": result.get("value"),
                "affected": result.get("affected"), "next_run_at": next_run,
                "notification_status": notif_status}
    except Exception as e:  # noqa: BLE001 — a failed run must not disable the alert
        err = str(e)[:300]
        log.exception("alert %s run failed", aid)
        store.finish_run(run_id, evaluated_value=None, condition_result=False,
                         previous_state=prev_state, current_state=bool(prev_state),
                         notification_sent=False, notification_status="error",
                         error_message=err)
        store.record_evaluation(user_id, aid, state=bool(prev_state), value=None,
                                next_run_at=next_run, triggered=False)
        return {"ok": False, "error": err, "next_run_at": next_run}


def _tick() -> None:
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        due = store.due_alerts(now_iso)
    except Exception:  # noqa: BLE001
        log.exception("due_alerts query failed")
        return
    for a in due:
        try:
            run_alert(a, manual=False)
        except Exception:  # noqa: BLE001
            log.exception("alert %s tick failed", a.get("id"))


def _loop() -> None:
    log.info("alerts scheduler started (tick=%ss)", _TICK_SECONDS)
    while True:
        try:
            _tick()
        except Exception:  # noqa: BLE001
            log.exception("alerts tick crashed (continuing)")
        time.sleep(_TICK_SECONDS)


def start() -> None:
    global _started
    if _started:
        return
    _started = True
    store.init()
    t = threading.Thread(target=_loop, name="alerts-scheduler", daemon=True)
    t.start()
