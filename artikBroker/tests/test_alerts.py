"""ArtikFinance Alerts — engine + store + API tests. Run with the artikAPIs venv:
    USERS_DB_PATH=/tmp/alerts_test.db DEV_AUTH_DISABLED=true \
      artikAPIs/venv/bin/python -m pytest artikBroker/tests/test_alerts.py -q
"""
import os
import sys
from datetime import datetime, timezone, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import alerts_engine as engine  # noqa: E402


# ── validation + allow-lists ──────────────────────────────────────────────────
def test_valid_alert_normalizes():
    a = engine.validate_alert({
        "name": "CC balance", "source": "payment_accounts",
        "filters": {"account_type": ["Credit Card"]},
        "conditions": [{"field": "total_current_balance", "operator": ">", "value": "25,000"}],
        "schedule": {"frequency": "daily", "time": "08:00", "timezone": "America/Los_Angeles"},
        "notification": {"channel": "slack", "destination_type": "channel", "destination": "artik"},
    })
    assert a["source_type"] == "payment_accounts"
    assert a["conditions"][0]["value"] == 25000.0
    assert a["notification"]["destination"] == "#artik"       # normalized with '#'
    assert a["trigger_mode"] == "state_change" and a["cooldown_minutes"] == 1440


@pytest.mark.parametrize("bad,msg", [
    ({"name": "", "source": "payment_accounts", "conditions": [{"field": "total_due", "operator": ">", "value": 1}], "schedule": {}, "notification": {}}, "name"),
    ({"name": "x", "source": "evil", "conditions": [{"field": "a", "operator": ">", "value": 1}], "schedule": {}, "notification": {}}, "source"),
    ({"name": "x", "source": "assets", "conditions": [{"field": "total_assets", "operator": "DROP TABLE", "value": 1}], "schedule": {}, "notification": {}}, "operator"),
    ({"name": "x", "source": "assets", "conditions": [{"field": "secret", "operator": ">", "value": 1}], "schedule": {}, "notification": {}}, "field"),
    ({"name": "x", "source": "assets", "conditions": [{"field": "total_assets", "operator": ">", "value": 1}], "schedule": {"frequency": "every_second"}, "notification": {}}, "frequency"),
    ({"name": "x", "source": "assets", "conditions": [{"field": "total_assets", "operator": ">", "value": 1}], "schedule": {"frequency": "daily", "time": "8am"}, "notification": {}}, "time"),
    ({"name": "x", "source": "assets", "conditions": [{"field": "total_assets", "operator": ">", "value": 1}], "schedule": {"frequency": "daily", "timezone": "Mars/Phobos"}, "notification": {}}, "timezone"),
])
def test_invalid_alerts_rejected(bad, msg):
    with pytest.raises(engine.AlertError) as e:
        engine.validate_alert(bad)
    assert msg in str(e.value).lower()


def test_sanitize_strips_html():
    assert "<script>" not in engine.sanitize_text("<script>alert(1)</script>MyAlert")


def test_row_operator_needs_row_field():
    with pytest.raises(engine.AlertError):
        engine.validate_alert({"name": "x", "source": "payment_accounts",
            "conditions": [{"field": "total_due", "operator": "within_days", "value": 5}],
            "schedule": {}, "notification": {}})


# ── scheduling ────────────────────────────────────────────────────────────────
def test_next_run_daily_is_future():
    nxt = engine.compute_next_run({"frequency": "daily", "time": "08:00", "timezone": "UTC"})
    assert datetime.fromisoformat(nxt.replace("Z", "+00:00")) > datetime.now(timezone.utc)


def test_next_run_frequencies():
    for f in ("hourly", "daily", "weekly", "monthly", "quarterly"):
        nxt = engine.compute_next_run({"frequency": f, "time": "09:00", "timezone": "UTC"})
        assert nxt.endswith("Z")


# ── operator evaluation (via _eval_condition on a synthetic ctx) ──────────────
def _ctx(scalars=None, rows=None, prev=None, affected=None):
    return {"scalars": scalars or {}, "rows": rows or [], "prev": prev or {},
            "affected": affected or []}


@pytest.mark.parametrize("op,cur,thr,want", [
    (">", 100, 50, True), (">", 40, 50, False), (">=", 50, 50, True),
    ("<", 40, 50, True), ("<=", 50, 50, True), ("=", 50, 50, True), ("!=", 51, 50, True),
])
def test_numeric_operators(op, cur, thr, want):
    met, _, _ = engine._eval_condition({"field": "x", "operator": op, "value": thr},
                                       _ctx(scalars={"x": cur}))
    assert met is want


def test_change_operators():
    ctx = _ctx(scalars={"total_assets": 90}, prev={"total_assets": 100})
    met, val, _ = engine._eval_condition(
        {"field": "total_assets", "operator": "percentage_decrease_greater_than", "value": 5}, ctx)
    assert met and val["current"] == 90
    met2, _, _ = engine._eval_condition(
        {"field": "total_assets", "operator": "percentage_increase_greater_than", "value": 5}, ctx)
    assert not met2
    met3, _, _ = engine._eval_condition(
        {"field": "total_assets", "operator": "absolute_change_greater_than", "value": 5}, ctx)
    assert met3


def test_within_days_and_overdue_rowwise():
    today = datetime.now(timezone.utc).date()
    rows = [
        {"due_date": (today + timedelta(days=3)).isoformat(), "remaining_amount_due": 100,
         "app_name": "Chase", "masked_account": "6697"},
        {"due_date": (today + timedelta(days=30)).isoformat(), "remaining_amount_due": 100,
         "app_name": "BofA", "masked_account": "1234"},
        {"due_date": (today - timedelta(days=10)).isoformat(), "remaining_amount_due": 50,
         "app_name": "Amex", "masked_account": "0005"},
    ]
    met, val, aff = engine._eval_condition(
        {"field": "due_date", "operator": "within_days", "value": 5}, _ctx(rows=rows))
    assert met and val["matched"] == 1 and aff[0]["label"] == "Chase ••••6697"
    meto, valo, _ = engine._eval_condition(
        {"field": "due_date", "operator": "overdue_by_days", "value": 5}, _ctx(rows=rows))
    assert meto and valo["matched"] == 1


def test_not_updated_for_days():
    old = (datetime.now(timezone.utc) - timedelta(days=40)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = [{"updated_at": old, "app_name": "Stale", "current_balance": 1}]
    met, _, _ = engine._eval_condition(
        {"field": "updated_at", "operator": "not_updated_for_days", "value": 30}, _ctx(rows=rows))
    assert met


def test_compound_and_or():
    a = engine.validate_alert({"name": "x", "source": "payment_accounts",
        "conditions": [{"field": "total_due", "operator": ">", "value": 100},
                       {"field": "minimum_due", "operator": ">", "value": 999999}],
        "logical_operator": "AND", "schedule": {}, "notification": {}})
    # monkeypatch resolve to a fixed ctx
    orig = engine.resolve
    engine.resolve = lambda s, f: _ctx(scalars={"total_due": 500, "minimum_due": 10})
    try:
        assert engine.evaluate(a)["state"] is False           # AND: second fails
        a["logical_operator"] = "OR"
        assert engine.evaluate(a)["state"] is True             # OR: first passes
    finally:
        engine.resolve = orig


# ── state-change + cooldown + modes ──────────────────────────────────────────
def test_state_change_default():
    a = {"trigger_mode": "state_change", "cooldown_minutes": 0}
    assert engine.should_notify(a, True, False, None)          # False->True fires
    assert not engine.should_notify(a, True, True, None)       # True->True suppressed
    assert not engine.should_notify(a, False, True, None)      # -> False no fire


def test_cooldown_blocks():
    recent = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    a = {"trigger_mode": "every_run", "cooldown_minutes": 60}
    assert not engine.should_notify(a, True, True, recent)     # inside cooldown
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert engine.should_notify(a, True, True, old)            # cooldown elapsed


def test_notify_modes():
    assert engine.should_notify({"trigger_mode": "every_run", "cooldown_minutes": 0}, True, True, None)
    assert engine.should_notify({"trigger_mode": "notify_once", "cooldown_minutes": 0}, True, False, None)
    assert not engine.should_notify({"trigger_mode": "notify_once", "cooldown_minutes": 0}, True, False,
                                    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))


# ── slack formatting masks + never leaks ─────────────────────────────────────
def test_slack_message_masks_and_formats():
    a = engine.validate_alert({"name": "CC alert", "source": "payment_accounts",
        "conditions": [{"field": "total_current_balance", "operator": ">", "value": 25000}],
        "schedule": {}, "notification": {}})
    result = {"value": 27450, "affected": [{"label": "BofA ••••1234", "amount": 22617}]}
    title, body, sev = engine.slack_message(a, result, "https://x.example.com")
    assert "$27,450" in body and "$25,000" in body and "BofA ••••1234" in body
    assert "1234567" not in body                                # no full numbers
    assert sev == "warning"


# ── store CRUD + ownership + soft delete ─────────────────────────────────────
def test_store_crud_and_ownership(tmp_path, monkeypatch):
    db = tmp_path / "alerts.db"
    monkeypatch.setenv("USERS_DB_PATH", str(db))
    import importlib
    import alerts_store
    importlib.reload(alerts_store)
    alert = engine.validate_alert({"name": "A", "source": "net_worth",
        "conditions": [{"field": "net_worth", "operator": "<", "value": 1000000}],
        "schedule": {}, "notification": {}})
    created = alerts_store.create(user_id=1, alert=alert, next_run_at="2030-01-01T00:00:00Z")
    assert created["id"] and created["name"] == "A"
    assert alerts_store.get(2, created["id"]) is None          # other user can't see it
    assert alerts_store.get(1, created["id"])["source_type"] == "net_worth"
    assert alerts_store.name_exists(1, "A") and not alerts_store.name_exists(1, "B")
    # pause / resume
    alerts_store.set_enabled(1, created["id"], False, None)
    assert alerts_store.get(1, created["id"])["is_enabled"] is False
    # run + notification history
    rid = alerts_store.create_run(created["id"], 1)
    alerts_store.finish_run(rid, evaluated_value=500000, condition_result=True, previous_state=False,
                            current_state=True, notification_sent=True, notification_status="sent")
    alerts_store.record_notification(created["id"], rid, 1, channel="slack",
                                     destination_type="default", destination="#artik",
                                     delivery_status="sent")
    h = alerts_store.history(1, created["id"])
    assert len(h["runs"]) == 1 and len(h["notifications"]) == 1
    # soft delete
    assert alerts_store.soft_delete(1, created["id"])
    assert alerts_store.get(1, created["id"]) is None
    assert alerts_store.get(1, created["id"], allow_deleted=True) is not None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
