"""Trading Desk engine tests — pure logic (universe, recommendation, risk, sizing)."""
import trading_desk as td


def _row(t, score, status="BUY", rsi=50, price=100, sector="Technology"):
    return {"ticker": t, "company": t, "score": score, "status": status, "rsi": rsi,
            "price": price, "sector": sector, "archetype": "COMPOUNDER"}


def test_universe_dedup_and_scope():
    pf = [{"ticker": "AAPL"}, {"ticker": "MSFT"}]
    # order = portfolio → sp500 → favorites, de-duped
    assert td.build_universe(pf, ["AAPL", "NVDA"], ["MSFT", "JNJ"], "all") == ["AAPL", "MSFT", "JNJ", "NVDA"]
    assert td.build_universe(pf, ["NVDA"], ["JNJ"], "favorites") == ["NVDA"]
    assert td.build_universe(pf, [], ["JNJ"], "portfolio") == ["AAPL", "MSFT"]


def test_new_position_recommendation_shape():
    ctx = td.portfolio_context([{"ticker": "AAPL", "value": 10000, "sector": "Technology"}])
    rec = td.make_recommendation(_row("MSFT", 82, price=400), None, ctx, td.DEFAULT_SETTINGS)
    assert rec["side"] == "BUY" and rec["category"] in ("New Position", "Momentum", "Pullback")
    assert rec["entry"] == 400 and rec["target"] > 400 > rec["stop"]
    assert rec["risk_reward"] and rec["suggested_shares"] >= 0
    assert "Artik Score 82/100" in rec["signals"]


def test_held_take_profit():
    ctx = td.portfolio_context([])
    held = {"ticker": "AAPL", "pl_pct": 40}
    rec = td.make_recommendation(_row("AAPL", 75), held, ctx, td.DEFAULT_SETTINGS)
    assert rec["category"] == "Take Profit" and rec["side"] == "SELL"


def test_risk_engine_rejects_low_score_and_reports_reason():
    ctx = td.portfolio_context([])
    rec = td.make_recommendation(_row("XYZ", 40, status="HOLD"), None, ctx, td.DEFAULT_SETTINGS)
    ok, reasons = td.risk_check(rec, td.DEFAULT_SETTINGS, ctx, {"trades_today": 0})
    assert not ok and reasons  # every rejection carries a reason


def test_risk_engine_respects_daily_cap():
    ctx = td.portfolio_context([])
    rec = td.make_recommendation(_row("NVDA", 90), None, ctx, td.DEFAULT_SETTINGS)
    ok, reasons = td.risk_check(rec, td.DEFAULT_SETTINGS, ctx, {"trades_today": 999})
    assert not ok and any("per day" in r for r in reasons)


def test_defaults_are_safe():
    assert td.DEFAULT_SETTINGS["trading_mode"] == "SCAN_ONLY"
    assert td.DEFAULT_SETTINGS["live_trading_enabled"] is False
    assert td.DEFAULT_SETTINGS["require_order_approval"] is True
    assert td.DEFAULT_SETTINGS["agent_enabled"] is False   # autonomy is opt-in


# ── exit engine (Phase 1) ─────────────────────────────────────────────────────
def _pos(**kw):
    return {"status": "open", "side": "BUY", "entry": 100.0, "stop": 92.0,
            "target": 115.0, "qty": 10, **kw}


def test_exit_stop_hit():
    action, _ = td.check_exit(_pos(), 91.5)
    assert action == "stop"


def test_exit_target_hit():
    action, _ = td.check_exit(_pos(), 115.2)
    assert action == "target"


def test_exit_holds_between_stop_and_target():
    action, upd = td.check_exit(_pos(), 105.0)
    assert action is None and upd["high_water"] == 105.0


def test_exit_trailing_stop_from_high_water():
    pos = _pos(high_water=112.0)
    action, _ = td.check_exit(pos, 104.0, trailing_pct=6.0)   # 112 * 0.94 = 105.28 > 104
    assert action == "trailing"


def test_exit_ignores_closed_positions():
    action, upd = td.check_exit(_pos(status="closed"), 50.0)
    assert action is None and upd == {}


# ── order queue (Phase 2) ─────────────────────────────────────────────────────
def test_order_queue_lifecycle(tmp_path):
    import trading_store as ts
    ts._DB_PATH = tmp_path / "users.db"   # isolate from the real DB
    o = ts.add_order({"ticker": "AAPL", "side": "BUY", "qty": 5, "source": "agent"})
    assert o["status"] == "pending_approval" and o["id"]
    ts.update_order(o["id"], {"status": "approved"})
    assert [x["id"] for x in ts.list_orders("approved")] == [o["id"]]
    ts.update_order(o["id"], {"status": "submitted", "result": {"ok": True}})
    got = ts.get_order(o["id"])
    assert got["status"] == "submitted" and got["result"] == {"ok": True}
    assert ts.list_orders("approved") == []
