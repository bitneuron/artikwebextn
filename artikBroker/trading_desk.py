"""Autonomous Trading Desk — universe, signal→recommendation engine, risk engine, sizing.

Pure/deterministic logic (no I/O) so it is easy to reason about and test. It consumes rows already
scored by the Artik engine (score/status/rsi/sector/archetype/price) plus the current Portfolio
holdings passed from the Portfolio page — it NEVER fetches holdings from IBKR. It produces
transparent recommendations (reason, confidence, entry/target/stop, R:R, sizing, signals) and never
implies guaranteed profit: it flags high-probability ideas under disciplined risk limits.
"""
from __future__ import annotations

from typing import Any

DEFAULT_SETTINGS: dict[str, Any] = {
    # mode / master switches (env overridable; live stays off + admin-gated at the API layer)
    "trading_mode": "SCAN_ONLY",   # SCAN_ONLY | PAPER_TRADING | LIVE_TRADING_WITH_APPROVAL | LIVE_TRADING_AUTO
    "paper_trading_enabled": True,
    "live_trading_enabled": False,
    "live_auto_trading_enabled": False,
    "require_order_approval": True,
    # autonomy (Phase 1): the server-side scheduler only runs when agent_enabled.
    "agent_enabled": False,
    "portfolio_key": "",           # server-side portfolio selection ("pf:<id>" / "xl:<file>" / "" = latest)
    "favorite_tickers": [],        # synced from the browser so the scheduler can include Favorites
    # cadence / caps
    "scan_interval_min": 15,
    "max_trades_per_day": 5,
    "max_open_positions": 20,
    # sizing / exposure / risk
    "max_position_size_pct": 10.0,       # single position as % of portfolio value
    "max_portfolio_exposure_pct": 90.0,
    "max_risk_per_trade_pct": 1.0,       # % of portfolio risked between entry and stop
    "max_daily_loss_pct": 3.0,
    "position_sizing": "risk",           # risk | atr | kelly | fixed
    # thresholds
    "min_confidence": 60,
    "min_artik_score": 65,
    # trade rules
    "default_stop_loss_pct": 8.0,
    "default_profit_target_pct": 15.0,
    "trailing_stop_pct": 6.0,
    "allow_short": False,
    "allow_margin": False,
    "allow_day_trades": False,
    "allow_swing_trades": True,
    "excluded_sectors": [],
    # accounts
    "paper_account_size": 100000.0,
    "ibkr_account": "",
}

LIVE_MODES = ("LIVE_TRADING_WITH_APPROVAL", "LIVE_TRADING_AUTO")
# Fields only an admin may change (live-trading + risk-limit governance).
ADMIN_ONLY_FIELDS = {
    "trading_mode", "live_trading_enabled", "live_auto_trading_enabled", "ibkr_account",
    "max_daily_loss_pct", "max_risk_per_trade_pct", "max_position_size_pct",
    "max_portfolio_exposure_pct", "allow_margin", "allow_short",
}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_universe(portfolio: list[dict], favorites: list[str], sp500: list[str],
                   scope: str = "all") -> list[str]:
    """Combined, de-duplicated ticker universe. scope: all|portfolio|sp500|favorites."""
    held = [(h.get("ticker") or "").upper() for h in portfolio if h.get("ticker")]
    fav = [(t or "").upper() for t in favorites if t]
    idx = [(t or "").upper() for t in sp500 if t]
    if scope == "portfolio":
        pool = held
    elif scope == "sp500":
        pool = idx
    elif scope == "favorites":
        pool = fav
    else:
        pool = held + idx + fav
    return list(dict.fromkeys([t for t in pool if t]))   # order-preserving dedupe


def portfolio_context(portfolio: list[dict]) -> dict:
    total = sum(_num(h.get("value")) or 0 for h in portfolio)
    by_sector: dict[str, float] = {}
    for h in portfolio:
        v = _num(h.get("value")) or 0
        by_sector[h.get("sector") or "Unknown"] = by_sector.get(h.get("sector") or "Unknown", 0) + v
    concentration = max(by_sector.values()) / total * 100 if total else 0
    return {"total_value": round(total, 2), "positions": len(portfolio),
            "sector_weights": {k: round(v / total * 100, 1) for k, v in by_sector.items()} if total else {},
            "top_sector": max(by_sector, key=by_sector.get) if by_sector else None,
            "concentration_pct": round(concentration, 1)}


def _confidence(row: dict, held: bool) -> int:
    score = _num(row.get("score")) or 0
    rsi = _num(row.get("rsi"))
    status = (row.get("status") or "").upper()
    conf = score                       # anchor on the Artik score
    if status == "BUY":
        conf += 8
    elif status == "SELL":
        conf -= 8
    if rsi is not None:
        if rsi < 30:
            conf += 6                  # overs'ld → mean-reversion tailwind
        elif rsi > 72:
            conf -= 6                  # overbought → chase risk
    return int(max(0, min(100, round(conf))))


def _category(row: dict, held: dict | None) -> tuple[str, str]:
    """Return (category, side)."""
    status = (row.get("status") or "").upper()
    rsi = _num(row.get("rsi"))
    pl_pct = _num((held or {}).get("pl_pct"))
    if held:
        if status == "SELL" or (pl_pct is not None and pl_pct >= 25):
            return ("Take Profit" if (pl_pct or 0) >= 25 else "Reduce Position", "SELL")
        if status == "BUY" and (_num(row.get("score")) or 0) >= 70:
            return ("Increase Position", "BUY")
        return ("Portfolio Improvement", "HOLD")
    # not held
    if rsi is not None and rsi < 35:
        return ("Pullback", "BUY")
    if rsi is not None and rsi > 60 and status == "BUY":
        return ("Momentum", "BUY")
    return ("New Position", "BUY")


def _signals(row: dict, held: dict | None) -> list[str]:
    out = []
    sc = _num(row.get("score"))
    if sc is not None:
        out.append(f"Artik Score {int(sc)}/100")
    if row.get("status"):
        out.append(f"Engine status: {row['status']}")
    rsi = _num(row.get("rsi"))
    if rsi is not None:
        zone = "oversold" if rsi < 30 else "overbought" if rsi > 70 else "neutral"
        out.append(f"RSI {rsi:.0f} ({zone})")
    if row.get("archetype"):
        out.append(f"Archetype: {row['archetype']}")
    if held:
        out.append("Already held — portfolio position")
    return out


def make_recommendation(row: dict, held: dict | None, ctx: dict, settings: dict) -> dict:
    price = _num(row.get("price"))
    category, side = _category(row, held)
    conf = _confidence(row, held is not None)
    stop_pct = _num(settings.get("default_stop_loss_pct")) or 8.0
    tgt_pct = _num(settings.get("default_profit_target_pct")) or 15.0

    entry = price
    if side == "SELL":
        target = round(entry * (1 - tgt_pct / 100), 2) if entry else None
        stop = round(entry * (1 + stop_pct / 100), 2) if entry else None
    else:
        target = round(entry * (1 + tgt_pct / 100), 2) if entry else None
        stop = round(entry * (1 - stop_pct / 100), 2) if entry else None
    rr = round(tgt_pct / stop_pct, 2) if stop_pct else None

    # position sizing (risk-based) — bounded by max position % of portfolio value
    total = _num(ctx.get("total_value")) or _num(settings.get("paper_account_size")) or 0
    risk_amt = total * (_num(settings.get("max_risk_per_trade_pct")) or 1.0) / 100
    per_share_risk = abs(entry - stop) if (entry and stop) else None
    shares = int(risk_amt / per_share_risk) if per_share_risk else 0
    max_by_pos = int((total * (_num(settings.get("max_position_size_pct")) or 10) / 100) / entry) if entry else 0
    shares = max(0, min(shares, max_by_pos) if max_by_pos else shares)
    dollar_alloc = round(shares * entry, 2) if entry else None

    sector = row.get("sector") or "Unknown"
    sector_wt = (ctx.get("sector_weights") or {}).get(sector)
    impact = (f"Adds to {sector} (now {sector_wt:.0f}% of book)" if sector_wt is not None and side == "BUY"
              else f"Trims {sector} exposure" if side == "SELL" else f"{sector} exposure")

    return {
        "ticker": row.get("ticker"),
        "company": row.get("company"),
        "sector": sector,
        "category": category,
        "side": side,
        "confidence": conf,
        "artik_score": int(_num(row.get("score")) or 0),
        "rsi": _num(row.get("rsi")),
        "status": row.get("status"),
        "archetype": row.get("archetype"),
        "held": bool(held),
        "entry": entry, "target": target, "stop": stop,
        "risk_reward": rr,
        "expected_return_pct": tgt_pct if side == "BUY" else round(tgt_pct, 1),
        "expected_risk_pct": stop_pct,
        "suggested_shares": shares,
        "dollar_allocation": dollar_alloc,
        "holding_period": "Swing (days–weeks)" if settings.get("allow_swing_trades") else "Position",
        "signals": _signals(row, held),
        "portfolio_impact": impact,
        "reason": _reason(category, row, held),
    }


def _reason(category: str, row: dict, held: dict | None) -> str:
    sc = int(_num(row.get("score")) or 0)
    st = row.get("status") or "—"
    t = row.get("ticker")
    if category == "Take Profit":
        return f"{t} shows a large unrealized gain and the engine rates it {st}; lock in profit and redeploy."
    if category == "Reduce Position":
        return f"Engine turned {st} on {t} (score {sc}); trim to control downside and free up risk budget."
    if category == "Increase Position":
        return f"{t} remains a high-quality holding (score {sc}, {st}); add on strength within limits."
    if category == "Pullback":
        return f"{t} is oversold with a solid score ({sc}); a pullback entry offers favorable risk/reward."
    if category == "Momentum":
        return f"{t} has momentum with an engine {st} (score {sc}); ride strength with a defined stop."
    if category == "Portfolio Improvement":
        return f"{t} is a hold; monitor — no edge to add or trim right now."
    return f"{t} scores {sc} ({st}) and is not yet held; a new position diversifies toward quality."


def check_exit(pos: dict, price: float, trailing_pct: float | None = None) -> tuple[str | None, dict]:
    """Exit engine (pure): given an open paper position and a live price, decide whether to close.

    Returns (action, updates): action is 'stop' | 'target' | 'trailing' | None; updates carries
    the new high-water mark to persist. Long (BUY) positions only — shorts are disabled by default.
    """
    if not price or pos.get("status") != "open":
        return (None, {})
    side = (pos.get("side") or "BUY").upper()
    stop, target = _num(pos.get("stop")), _num(pos.get("target"))
    hw = max(_num(pos.get("high_water")) or 0, _num(pos.get("entry")) or 0, price)
    updates = {"high_water": hw}
    if side == "BUY":
        if stop and price <= stop:
            return ("stop", updates)
        if target and price >= target:
            return ("target", updates)
        if trailing_pct and hw and price <= hw * (1 - trailing_pct / 100) and price > (stop or 0):
            return ("trailing", updates)
    else:  # defensive: short positions mirror the checks
        if stop and price >= stop:
            return ("stop", updates)
        if target and price <= target:
            return ("target", updates)
    return (None, updates)


def risk_check(rec: dict, settings: dict, ctx: dict, state: dict) -> tuple[bool, list[str]]:
    """Reject trades that violate configured limits — each rejection carries a reason."""
    reasons: list[str] = []
    if state.get("killed"):
        reasons.append("Emergency kill switch is active")
    if state.get("paused"):
        reasons.append("Trading agent is paused")
    if rec["side"] == "HOLD":
        reasons.append("No actionable edge (hold)")
    if rec["confidence"] < (settings.get("min_confidence") or 0):
        reasons.append(f"Confidence {rec['confidence']}% below minimum {settings.get('min_confidence')}%")
    if rec["side"] == "BUY" and rec["artik_score"] < (settings.get("min_artik_score") or 0):
        reasons.append(f"Artik score {rec['artik_score']} below minimum {settings.get('min_artik_score')}")
    if rec["sector"] in (settings.get("excluded_sectors") or []):
        reasons.append(f"Sector '{rec['sector']}' is excluded")
    if (state.get("trades_today") or 0) >= (settings.get("max_trades_per_day") or 999):
        reasons.append("Max trades per day reached")
    if rec["side"] == "BUY" and (ctx.get("positions") or 0) >= (settings.get("max_open_positions") or 999) and not rec["held"]:
        reasons.append("Max open positions reached")
    if rec["side"] == "SHORT" and not settings.get("allow_short"):
        reasons.append("Short selling is disabled")
    if not rec.get("entry"):
        reasons.append("No live price available")
    return (len(reasons) == 0, reasons)
