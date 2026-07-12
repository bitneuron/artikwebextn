"""Autonomous Trading Desk scheduler — Phase 1 of autonomy.

A daemon thread that, when the agent is enabled (Agent Settings → agent_enabled) and not
paused/killed, runs a full cycle every `scan_interval_min`:

    exits → load portfolio (server-side snapshot) → scan universe → mode dispatch
      SCAN_ONLY                  log + Slack the top opportunities (no trades)
      PAPER_TRADING              auto-open paper trades for risk-passed BUY recs
      LIVE_TRADING_WITH_APPROVAL enqueue live orders as pending_approval (human approves)
      LIVE_TRADING_AUTO          enqueue live orders pre-approved (admin-only mode)

The exit engine runs EVERY tick (30s cadence, cheap) so stops/targets/trailing stops on open
paper positions are honored promptly, not just at scan time. Holdings are never fetched from
IBKR — the Portfolio page snapshots are the source of truth; IBKR is execution-only (Phase 2
bridge). Dependencies (scan core, portfolio loader) are injected by app.py to avoid circular
imports. All notifications go through the existing Artik Notifier → Slack hook and never raise.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

import trading_desk
import trading_store

log = logging.getLogger("trading.scheduler")

_TICK_SECONDS = 30
_started = False


def _notify(msg: str, status: str = "completed") -> None:
    try:
        from notifications import notify_agent_terminal
        notify_agent_terminal(agent_name="Trading Desk", status=status, task_name=msg)
    except Exception:  # noqa: BLE001 — notifications must never break the loop
        pass


def _last_price(ticker: str) -> float | None:
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        px = None
        try:
            px = t.fast_info.last_price
        except Exception:  # noqa: BLE001
            pass
        if not px:
            hist = t.history(period="1d")
            if len(hist):
                px = float(hist["Close"].iloc[-1])
        return round(float(px), 2) if px else None
    except Exception:  # noqa: BLE001
        return None


def run_exits() -> list[dict]:
    """Check every open paper position against live prices; auto-close on stop/target/trailing."""
    settings = trading_store.get_settings()
    trailing = settings.get("trailing_stop_pct")
    closed = []
    for pos in trading_store.list_paper(status="open"):
        px = _last_price(pos.get("ticker") or "")
        if not px:
            continue
        action, updates = trading_desk.check_exit(pos, px, trailing)
        if updates:
            trading_store.update_paper(pos["id"], updates)
        if action:
            done = trading_store.close_paper(pos["id"], px)
            if done:
                closed.append({**done, "exit_reason": action})
                trading_store.log_decision({"event": "paper_exit", "ticker": done["ticker"],
                                            "reason": action, "pl": done["realized_pl"]})
                _notify(f"Paper exit ({action}): {done['side']} {done['qty']} {done['ticker']} "
                        f"@ ${px} → P/L ${done['realized_pl']}")
    return closed


def _open_paper_entries(recs: list[dict], settings: dict) -> int:
    """Auto-open paper positions for the strongest risk-passed BUY recommendations."""
    open_tickers = {p.get("ticker") for p in trading_store.list_paper(status="open")}
    opened = 0
    for rec in recs:
        st = trading_store.get_state()
        if (st.get("trades_today") or 0) >= (settings.get("max_trades_per_day") or 0):
            break
        if len(open_tickers) >= (settings.get("max_open_positions") or 0):
            break
        if rec["side"] != "BUY" or not rec.get("risk_ok") or rec["ticker"] in open_tickers:
            continue
        qty = rec.get("suggested_shares") or 0
        if not qty or not rec.get("entry"):
            continue
        trading_store.add_paper({
            "ticker": rec["ticker"], "company": rec.get("company"), "side": "BUY",
            "qty": qty, "entry": rec["entry"], "target": rec.get("target"),
            "stop": rec.get("stop"), "category": rec.get("category"),
            "confidence": rec.get("confidence"), "mode": "paper", "opened_by": "agent"})
        trading_store.set_state({"trades_today": (st.get("trades_today") or 0) + 1})
        trading_store.log_decision({"event": "paper_entry", "ticker": rec["ticker"],
                                    "qty": qty, "entry": rec["entry"], "confidence": rec["confidence"]})
        _notify(f"Paper entry: BUY {qty} {rec['ticker']} @ ${rec['entry']} "
                f"(target ${rec.get('target')}, stop ${rec.get('stop')}, {rec['confidence']}% conf — {rec['category']})")
        open_tickers.add(rec["ticker"])
        opened += 1
    return opened


def _enqueue_live_orders(recs: list[dict], settings: dict, auto: bool) -> int:
    """Queue live order candidates for the Mac execution bridge (Phase 2)."""
    pending = {o.get("ticker") for o in trading_store.list_orders()
               if o.get("status") in ("pending_approval", "approved", "submitted")}
    queued = 0
    for rec in recs:
        st = trading_store.get_state()
        if (st.get("trades_today") or 0) >= (settings.get("max_trades_per_day") or 0):
            break
        if not rec.get("risk_ok") or rec["side"] not in ("BUY", "SELL") or rec["ticker"] in pending:
            continue
        qty = rec.get("suggested_shares") or 0
        if not qty:
            continue
        trading_store.add_order({
            "ticker": rec["ticker"], "company": rec.get("company"), "side": rec["side"],
            "qty": qty, "account_id": settings.get("ibkr_account") or "",
            "status": "approved" if auto else "pending_approval", "source": "agent",
            "rec": {k: rec.get(k) for k in ("entry", "target", "stop", "confidence",
                                            "category", "reason", "artik_score")}})
        trading_store.set_state({"trades_today": (st.get("trades_today") or 0) + 1})
        trading_store.log_decision({"event": "live_queued", "ticker": rec["ticker"],
                                    "side": rec["side"], "auto": auto})
        _notify(f"Live order {'AUTO-approved' if auto else 'awaiting approval'}: "
                f"{rec['side']} {qty} {rec['ticker']} @ ~${rec.get('entry')} ({rec['confidence']}% conf). "
                f"{'Bridge will execute.' if auto else 'Approve in Trading Desk → Orders.'}")
        pending.add(rec["ticker"])
        queued += 1
    return queued


def run_cycle(scan_core, load_portfolio) -> dict:
    """One full autonomous cycle. Returns a summary dict (also logged)."""
    settings = trading_store.get_settings()
    mode = settings.get("trading_mode") or "SCAN_ONLY"
    closed = run_exits()

    portfolio = []
    try:
        portfolio = load_portfolio(settings.get("portfolio_key") or "") or []
    except Exception as e:  # noqa: BLE001
        log.warning("portfolio load failed: %s", e)
    favorites = settings.get("favorite_tickers") or []
    if not portfolio and not favorites:
        trading_store.log_decision({"event": "auto_scan_skipped", "reason": "no portfolio or favorites"})
        return {"skipped": "no portfolio or favorites"}

    result = scan_core(portfolio, favorites, "all")
    recs = result.get("recommendations") or []

    opened = queued = 0
    if mode == "PAPER_TRADING" and settings.get("paper_trading_enabled"):
        opened = _open_paper_entries(recs, settings)
    elif mode in trading_desk.LIVE_MODES and settings.get("live_trading_enabled"):
        auto = (mode == "LIVE_TRADING_AUTO" and settings.get("live_auto_trading_enabled"))
        queued = _enqueue_live_orders(recs, settings, auto)

    top = ", ".join(f"{r['ticker']} {r['confidence']}%" for r in recs[:5]) or "none"
    summary = {"event": "auto_scan", "mode": mode, "recommendations": len(recs),
               "rejected": len(result.get("rejected") or []), "paper_opened": opened,
               "live_queued": queued, "exits": len(closed), "top": top}
    trading_store.log_decision(summary)
    if recs or closed:
        _notify(f"Scan done ({mode}): {len(recs)} opportunities (top: {top}); "
                f"{opened} paper entries, {queued} live queued, {len(closed)} exits.")
    return summary


def start(scan_core, load_portfolio) -> None:
    """Start the daemon (idempotent). scan_core(portfolio, favorites, scope) and
    load_portfolio(key) are injected by app.py."""
    global _started
    if _started:
        return
    _started = True

    def _loop():
        log.info("Trading Desk scheduler started (tick %ss)", _TICK_SECONDS)
        while True:
            time.sleep(_TICK_SECONDS)
            try:
                st = trading_store.rollover_day()
                settings = trading_store.get_settings()
                if not settings.get("agent_enabled") or st.get("killed") or st.get("paused"):
                    continue
                # Exits run every tick; the full scan only when due.
                run_exits()
                last = st.get("last_auto_scan")
                interval = max(1, int(settings.get("scan_interval_min") or 15)) * 60
                now = datetime.now(timezone.utc).timestamp()
                last_ts = datetime.fromisoformat(last).timestamp() if last else 0
                if now - last_ts >= interval:
                    trading_store.set_state({"last_auto_scan": trading_store._now()})
                    run_cycle(scan_core, load_portfolio)
            except Exception:  # noqa: BLE001 — the loop must survive anything
                log.exception("trading scheduler tick failed")

    threading.Thread(target=_loop, daemon=True, name="trading-desk-scheduler").start()
