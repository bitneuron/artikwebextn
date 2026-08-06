"""Multi-Snapshot Portfolio Analysis — consolidation + comparison engine.

Combines several saved portfolio snapshots (E*TRADE / Schwab / IBKR / Excel) into one
consolidated portfolio, or compares them, following strict aggregation rules:

  * merge holdings by a NORMALIZED security id (CUSIP → exact ticker → ticker+type+exchange;
    stored snapshots only carry the ticker, so we key on the normalized ticker and keep
    options / share-classes separate);
  * sum quantities, market values, cost bases from RAW numeric values — never display strings;
  * compute aggregate percentages from aggregate dollar totals (never average percentages);
  * missing fields are surfaced as "Unavailable", never coerced to 0;
  * every value keeps its source + masked-account attribution;
  * reconcile the sum of recorded snapshot values against the computed consolidated value.

Snapshots persist only `{ticker, qty, cost_basis}` per holding plus recorded totals, so
per-holding PRICE / market value / day-change / CUSIP are not stored — those are marked
Unavailable and (for market value) computed from live prices via an injected `enrich`
callback, which is disclosed in the data-quality section. The engine imports nothing from
the web app, so it is unit-testable in isolation.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

UNAVAILABLE = "Unavailable"

# Cash / money-market tickers that represent a balance, not a priced equity position.
_CASH_TICKERS = {
    "CASH", "USD", "$CASH", "MMDA", "MMF", "FDIC", "BANK",
    "SPAXX", "FDRXX", "VMFXX", "SWVXX", "SNVXX", "SPRXX", "FZFXX", "VMRXX", "TIMXX",
}
_ETF_HINTS = {"SPY", "QQQ", "VOO", "VTI", "IVV", "ARKK", "DIA", "IWM", "EEM", "EFA",
              "XLK", "XLF", "XLE", "GLD", "SLV", "TLT", "HYG", "SCHD", "VUG", "VYM"}
# OCC option symbol, e.g. "AAPL  260116C00190000" or "AAPL 01/16/26 190 C"
_OPTION_RE = re.compile(r"\s")


def _num(v):
    """Parse to float, or None (never 0) for missing/blank/non-numeric."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v) if v == v else None  # drop NaN
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


def _masked(account_ending: str | None) -> str:
    a = (account_ending or "").strip()
    return f"••{a}" if a else "••????"


def normalize_symbol(raw: str) -> tuple[str, str]:
    """Return (normalized_key, asset_type). Options keep their full symbol so different
    underlyings / expirations / strikes / call-put never merge; equities normalize to the
    bare upper-case ticker; cash/money-market map to a 'cash' type."""
    s = (raw or "").strip().upper()
    if not s:
        return "", "unknown"
    if s in _CASH_TICKERS:
        return s, "cash"
    if _OPTION_RE.search(s):                      # any whitespace ⇒ treat as option/complex id
        return s, "option"
    if s.endswith("=X") or "/" in s:             # FX / pair
        return s, "fx"
    if s.endswith("-USD") or s in {"BTC", "ETH", "DOGE", "SOL"}:
        return s, "crypto"
    if s in _ETF_HINTS:
        return s, "etf"
    return s, "equity"


def _iso(ts: str | None) -> str:
    return (ts or "").strip()


def scope_of(snapshots: list[dict]) -> list[dict]:
    """The 'Analysis scope' block — one row per included snapshot."""
    out = []
    for s in snapshots:
        out.append({
            "snapshot_id": s.get("id"),
            "key": f"pf:{s.get('id')}",
            "source": s.get("source"),
            "label": s.get("label") or s.get("source"),
            "masked_account": _masked(s.get("account_ending")),
            "timestamp": _iso(s.get("created_at")),
            "recorded_value": _num(s.get("total_value")),
            "recorded_gain": _num(s.get("total_gain")),
            "positions": len(s.get("holdings") or []),
        })
    return out


def detect_duplicate_accounts(snapshots: list[dict]) -> list[dict]:
    """Same (source, account) selected more than once ⇒ likely different dates for the same
    account. Consolidating those double-counts the portfolio — caller should warn."""
    by_acct: dict[tuple, list[dict]] = {}
    for s in snapshots:
        key = (s.get("source"), (s.get("account_ending") or "").strip())
        by_acct.setdefault(key, []).append(s)
    dups = []
    for (source, acct), snaps in by_acct.items():
        if len(snaps) > 1:
            dups.append({
                "source": source, "masked_account": _masked(acct),
                "snapshot_ids": [x.get("id") for x in snaps],
                "timestamps": sorted(_iso(x.get("created_at")) for x in snaps),
            })
    return dups


def _price_timestamps(snapshots: list[dict]) -> list[str]:
    return sorted({_iso(s.get("created_at")) for s in snapshots if _iso(s.get("created_at"))})


def consolidate(snapshots: list[dict], base_currency: str = "USD", enrich=None) -> dict:
    """Combine snapshots into one portfolio. `enrich(tickers)` → {TICKER: {price, name,
    sector, asset_class, day_change}} supplies live prices/metadata (snapshots store none);
    absent, market value is Unavailable. Returns the full structured result."""
    snapshots = list(snapshots or [])
    base_currency = (base_currency or "USD").upper()
    warnings: list[str] = []
    dq_missing: set[str] = set()
    dq_notes: list[str] = []

    dups = detect_duplicate_accounts(snapshots)
    if dups:
        warnings.append(
            "Multiple snapshots from the same account are selected "
            + "; ".join(f"{d['source']} {d['masked_account']} ({len(d['timestamps'])} dates)" for d in dups)
            + ". Consolidating may DOUBLE-COUNT that account — keep one snapshot per account, "
              "or switch to Compare mode for a historical view.")

    # Enrich prices/metadata for every distinct plain ticker (skip options/cash for pricing).
    tickers = sorted({(h.get("ticker") or "").strip().upper()
                      for s in snapshots for h in (s.get("holdings") or [])
                      if (h.get("ticker") or "").strip()})
    meta: dict[str, dict] = {}
    if enrich and tickers:
        try:
            meta = enrich(tickers) or {}
        except Exception as e:  # noqa: BLE001 — never fail consolidation on enrichment
            dq_notes.append(f"Live enrichment unavailable ({type(e).__name__}); prices marked Unavailable.")
            meta = {}
    # ── merge holdings by normalized id ──────────────────────────────────────
    merged: dict[str, dict] = {}
    conflicts: list[dict] = []
    total_cash = 0.0
    cash_available = False
    for s in snapshots:
        src, acct = s.get("source"), _masked(s.get("account_ending"))
        for h in (s.get("holdings") or []):
            raw = (h.get("ticker") or "").strip()
            if not raw:
                continue
            key, atype = normalize_symbol(raw)
            if not key:
                continue
            qty = _num(h.get("qty"))
            cost = _num(h.get("cost_basis"))
            if atype == "cash":
                cv = _num(h.get("market_value"))
                cv = cv if cv is not None else qty
                if cv is not None:             # a cash *position* (use recorded value, else qty)
                    total_cash += cv
                    cash_available = True
                continue                       # never treat cash as a priced security
            m = merged.get(key)
            if m is None:
                m = merged[key] = {
                    "symbol": key, "asset_type": atype,
                    "name": h.get("name") or (meta.get(key) or {}).get("name") or key,
                    "sector": (meta.get(key) or {}).get("sector") or UNAVAILABLE,
                    "asset_class": (meta.get(key) or {}).get("asset_class") or atype,
                    "qty": 0.0, "cost_basis": 0.0, "cost_available": False,
                    "live_price": (meta.get(key) or {}).get("price"),
                    "rec_mv": 0.0, "rec_mv_n": 0, "instances": 0,
                    "rec_day": 0.0, "rec_day_n": 0, "rec_price": None,
                    "cusips": set(), "sources": {}, "raw_symbols": set(),
                }
            else:
                # Same key but a different asset type ⇒ flag rather than silently merge.
                if m["asset_type"] != atype:
                    conflicts.append({"symbol": key, "types": sorted({m["asset_type"], atype})})
                if m["name"] == key and h.get("name"):
                    m["name"] = h["name"]
            m["instances"] += 1
            m["qty"] += (qty or 0.0)
            if cost is not None:
                m["cost_basis"] += cost
                m["cost_available"] = True
            # Recorded per-holding values (snapshot-time; preferred over live prices).
            rmv, rpr, rday = _num(h.get("market_value")), _num(h.get("price")), _num(h.get("day_change"))
            if rmv is not None:
                m["rec_mv"] += rmv
                m["rec_mv_n"] += 1
            if rpr is not None:
                m["rec_price"] = rpr
            if rday is not None:
                m["rec_day"] += rday
                m["rec_day_n"] += 1
            cu = (h.get("cusip") or "").strip()
            if cu:
                m["cusips"].add(cu)
            m["raw_symbols"].add(raw)
            slot = m["sources"].setdefault((src, acct), {"qty": 0.0, "cost_basis": None})
            slot["qty"] += (qty or 0.0)
            if cost is not None:
                slot["cost_basis"] = (slot["cost_basis"] or 0.0) + cost

    # ── per-holding rows + aggregate dollars (RAW) ───────────────────────────
    holdings: list[dict] = []
    agg_mv = 0.0
    agg_cost = 0.0
    agg_cost_partial = False
    agg_day = 0.0
    agg_day_available = False
    price_bases: set[str] = set()
    for key, m in merged.items():
        # Prefer RECORDED market value (snapshot-time) when every instance carried one;
        # otherwise derive from a recorded price, else fall back to a live price.
        if m["rec_mv_n"] and m["rec_mv_n"] == m["instances"]:
            mv = round(m["rec_mv"], 2)
            price = m["rec_price"] if m["rec_price"] is not None else (
                round(mv / m["qty"], 4) if m["qty"] else None)
            price_bases.add("recorded")
        else:
            price = m["rec_price"] if m["rec_price"] is not None else _num(m.get("live_price"))
            mv = round(price * m["qty"], 2) if (price is not None) else None
            price_bases.add("recorded" if m["rec_price"] is not None else ("live" if price is not None else "none"))
        if mv is None:
            dq_missing.add("current price")
        # CUSIP conflict: same ticker key resolving to >1 CUSIP ⇒ flag, don't trust the merge.
        if len(m["cusips"]) > 1:
            conflicts.append({"symbol": key, "cusips": sorted(m["cusips"]),
                              "note": "same ticker maps to multiple CUSIPs across snapshots"})
        cost = round(m["cost_basis"], 2) if m["cost_available"] else None
        if cost is None:
            dq_missing.add("cost basis")
        gain = round(mv - cost, 2) if (mv is not None and cost is not None) else None
        gain_pct = round(gain / cost * 100, 2) if (gain is not None and cost) else None
        day = round(m["rec_day"], 2) if m["rec_day_n"] else None
        if day is not None:
            agg_day += day
            agg_day_available = True
        if mv is not None:
            agg_mv += mv
        if cost is not None:
            agg_cost += cost
        else:
            agg_cost_partial = True
        holdings.append({
            "symbol": key, "name": m["name"], "asset_type": m["asset_type"],
            "sector": m["sector"], "asset_class": m["asset_class"],
            "cusip": (sorted(m["cusips"])[0] if len(m["cusips"]) == 1 else (UNAVAILABLE if not m["cusips"] else "conflict")),
            "qty": round(m["qty"], 6),
            "price": round(price, 2) if price is not None else UNAVAILABLE,
            "market_value": mv if mv is not None else UNAVAILABLE,
            "cost_basis": cost if cost is not None else UNAVAILABLE,
            "gain": gain if gain is not None else UNAVAILABLE,
            "gain_pct": gain_pct if gain_pct is not None else UNAVAILABLE,
            "day_change": day if day is not None else UNAVAILABLE,
            "sources": [{"source": src, "account": acct,
                         "qty": round(v["qty"], 6),
                         "cost_basis": (round(v["cost_basis"], 2) if v["cost_basis"] is not None else UNAVAILABLE)}
                        for (src, acct), v in sorted(m["sources"].items())],
        })
    # portfolio weights from aggregate market value
    denom = agg_mv + (total_cash if cash_available else 0.0)
    for h in holdings:
        mv = h["market_value"]
        h["weight_pct"] = round(mv / denom * 100, 2) if (isinstance(mv, (int, float)) and denom) else UNAVAILABLE
    holdings.sort(key=lambda h: (h["market_value"] if isinstance(h["market_value"], (int, float)) else -1),
                  reverse=True)

    total_gain = round(agg_mv - agg_cost, 2) if not agg_cost_partial else (
        round(agg_mv - agg_cost, 2))  # partial-cost still reported, flagged below
    total_gain_pct = round((agg_mv - agg_cost) / agg_cost * 100, 2) if agg_cost else None
    if agg_cost_partial:
        dq_notes.append("Some holdings have no cost basis; combined cost/gain exclude them "
                        "(not counted as zero) — see per-holding 'Unavailable' cost.")

    accounts = sorted({(s.get("source"), _masked(s.get("account_ending"))) for s in snapshots})
    day_total = round(agg_day, 2) if agg_day_available else None
    day_pct = (round(agg_day / (agg_mv - agg_day) * 100, 2)
               if (agg_day_available and (agg_mv - agg_day)) else None)
    summary = {
        "market_value": round(agg_mv, 2) if agg_mv else UNAVAILABLE,
        "cost_basis": round(agg_cost, 2) if agg_cost else UNAVAILABLE,
        "unrealized_gain": total_gain if agg_cost else UNAVAILABLE,
        "unrealized_gain_pct": total_gain_pct if total_gain_pct is not None else UNAVAILABLE,
        "day_change": day_total if day_total is not None else UNAVAILABLE,
        "day_change_pct": day_pct if day_pct is not None else UNAVAILABLE,
        "cash": round(total_cash, 2) if cash_available else UNAVAILABLE,
        "invested_value": round(agg_mv, 2) if agg_mv else UNAVAILABLE,
        "n_unique_securities": len(holdings),
        "n_accounts": len(accounts),
        "n_snapshots": len(snapshots),
        "base_currency": base_currency,
    }

    # ── allocation (by sector / asset class / source / account / security) ────
    def _alloc(field_fn):
        buckets: dict[str, float] = {}
        for h in holdings:
            mv = h["market_value"]
            if isinstance(mv, (int, float)):
                buckets[field_fn(h)] = buckets.get(field_fn(h), 0.0) + mv
        tot = sum(buckets.values()) or 1.0
        return [{"label": k, "value": round(v, 2), "pct": round(v / tot * 100, 2)}
                for k, v in sorted(buckets.items(), key=lambda kv: -kv[1])]

    by_source_acct: dict[tuple, dict] = {}
    for h in holdings:
        for sc in h["sources"]:
            k = (sc["source"], sc["account"])
            b = by_source_acct.setdefault(k, {"market_value": 0.0, "cost_basis": 0.0, "cost_avail": False})
            price = _num(h["price"]) if isinstance(h["price"], (int, float)) else None
            if price is not None and sc["qty"]:
                b["market_value"] += price * sc["qty"]
            if isinstance(sc["cost_basis"], (int, float)):
                b["cost_basis"] += sc["cost_basis"]; b["cost_avail"] = True
    source_account_breakdown = [
        {"source": k[0], "account": k[1],
         "market_value": round(v["market_value"], 2),
         "cost_basis": round(v["cost_basis"], 2) if v["cost_avail"] else UNAVAILABLE,
         "weight_pct": round(v["market_value"] / (agg_mv or 1) * 100, 2)}
        for k, v in sorted(by_source_acct.items(), key=lambda kv: -kv[1]["market_value"])]

    allocation = {
        "by_security": [{"label": h["symbol"], "value": h["market_value"], "pct": h["weight_pct"]}
                        for h in holdings[:25] if isinstance(h["market_value"], (int, float))],
        "by_sector": _alloc(lambda h: h["sector"] if h["sector"] != UNAVAILABLE else "Unavailable"),
        "by_asset_class": _alloc(lambda h: h["asset_class"] or "unknown"),
        "by_source": _alloc(lambda h: h["sources"][0]["source"] if h["sources"] else "unknown"),
        "by_account": [{"label": f"{b['source']} {b['account']}", "value": b["market_value"],
                        "pct": b["weight_pct"]} for b in source_account_breakdown],
    }

    # ── risks / opportunities ────────────────────────────────────────────────
    priced = [h for h in holdings if isinstance(h["market_value"], (int, float))]
    gains = [h for h in holdings if isinstance(h["gain"], (int, float))]
    top = priced[:5]
    concentration = {
        "top1_pct": priced[0]["weight_pct"] if priced else UNAVAILABLE,
        "top5_pct": round(sum(h["market_value"] for h in top) / denom * 100, 2) if (priced and denom) else UNAVAILABLE,
        "flags": [],
    }
    if priced and isinstance(priced[0]["weight_pct"], (int, float)) and priced[0]["weight_pct"] >= 20:
        concentration["flags"].append(
            f"{priced[0]['symbol']} is {priced[0]['weight_pct']}% of the portfolio — high single-name concentration.")
    if isinstance(concentration["top5_pct"], (int, float)) and concentration["top5_pct"] >= 50:
        concentration["flags"].append(f"Top 5 holdings are {concentration['top5_pct']}% of the portfolio.")
    duplicates = [{"symbol": h["symbol"], "accounts": [f"{s['source']} {s['account']}" for s in h["sources"]]}
                  for h in holdings if len(h["sources"]) > 1]
    risks = {
        "largest_positions": [{"symbol": h["symbol"], "market_value": h["market_value"], "weight_pct": h["weight_pct"]} for h in top],
        "biggest_gains": [{"symbol": h["symbol"], "gain": h["gain"], "gain_pct": h["gain_pct"]}
                          for h in sorted(gains, key=lambda x: x["gain"], reverse=True)[:5]],
        "biggest_losses": [{"symbol": h["symbol"], "gain": h["gain"], "gain_pct": h["gain_pct"]}
                           for h in sorted(gains, key=lambda x: x["gain"])[:5] if h["gain"] < 0],
        "concentration": concentration,
        "duplicated_across_accounts": duplicates,
    }

    # ── reconciliation: recorded snapshot totals vs computed consolidated ─────
    recorded = [(_num(s.get("total_value"))) for s in snapshots]
    sum_recorded = round(sum(v for v in recorded if v is not None), 2) if any(v is not None for v in recorded) else None
    recon_diff = round(agg_mv - sum_recorded, 2) if (sum_recorded is not None and agg_mv) else None
    reconciliation = {
        "sum_recorded_value": sum_recorded if sum_recorded is not None else UNAVAILABLE,
        "consolidated_market_value": round(agg_mv, 2) if agg_mv else UNAVAILABLE,
        "difference": recon_diff if recon_diff is not None else UNAVAILABLE,
        "difference_pct": (round(recon_diff / sum_recorded * 100, 2)
                           if (recon_diff is not None and sum_recorded) else UNAVAILABLE),
        "explanation": ("The consolidated value is the sum of per-holding values; the difference vs "
                        "the recorded snapshot account totals reflects the price basis (snapshot-time "
                        "recorded vs live), any unpriced securities, cash accounting, or accrued "
                        "interest. With recorded prices this is typically near zero."
                        if recon_diff is not None else
                        "Snapshot recorded totals unavailable for one or more snapshots."),
    }

    # Overall price basis: recorded (snapshot-time) / live (computed) / mixed.
    live_used = "live" in price_bases
    rec_used = "recorded" in price_bases
    price_basis = ("recorded" if (rec_used and not live_used) else
                   ("mixed" if (rec_used and live_used) else
                    ("live" if live_used else "unavailable")))
    if price_basis == "recorded":
        dq_notes.append("Market values use each snapshot's RECORDED prices (point-in-time) — no live "
                        "substitution.")
    elif price_basis == "mixed":
        dq_notes.append("Some holdings use recorded snapshot prices and some (older snapshots without "
                        "stored prices) use LIVE prices — disclosed here.")
    elif price_basis == "live":
        dq_notes.append("These snapshots predate per-holding price capture; market values are computed "
                        "from LIVE prices, not the snapshot-time price.")
    if not agg_day_available:
        dq_notes.append("Day change is unavailable for these snapshots (only captured for snapshots "
                        "taken after the recorded-fields update, and E*TRADE/Schwab feeds).")

    price_ts = _price_timestamps(snapshots)
    if len(price_ts) > 1:
        dq_notes.append(f"Selected snapshots have different timestamps ({', '.join(price_ts)}); "
                        "figures are not from a single point in time.")
    missing = sorted(dq_missing)
    if not agg_day_available:
        missing.append("day change (not in these snapshots)")
    data_quality = {
        "price_basis": price_basis,
        "price_timestamps": price_ts,
        "missing_fields": missing,
        "notes": dq_notes,
        "conflicting_mappings": conflicts,
        "base_currency": base_currency,
        "currency_note": ("All snapshots assumed to be in the base currency; per-holding currency is "
                          "not stored, so no FX conversion was applied. If any account is non-USD, "
                          "values may need conversion." ),
    }

    return {
        "mode": "consolidate",
        "base_currency": base_currency,
        "scope": scope_of(snapshots),
        "summary": summary,
        "holdings": holdings,
        "source_account_breakdown": source_account_breakdown,
        "allocation": allocation,
        "risks": risks,
        "data_quality": data_quality,
        "reconciliation": reconciliation,
        "warnings": warnings,
    }


def compare(snapshots: list[dict], base_currency: str = "USD", enrich=None) -> dict:
    """Keep snapshots separate and diff them (value / holdings / new & closed positions /
    price-vs-position driven). Ordered oldest → newest by timestamp."""
    snaps = sorted(snapshots or [], key=lambda s: _iso(s.get("created_at")))
    base_currency = (base_currency or "USD").upper()

    per_snapshot = []
    holding_maps = []
    for s in snaps:
        hmap: dict[str, dict] = {}
        for h in (s.get("holdings") or []):
            key, atype = normalize_symbol((h.get("ticker") or "").strip())
            if not key or atype == "cash":
                continue
            slot = hmap.setdefault(key, {"qty": 0.0, "cost": 0.0, "cost_avail": False})
            slot["qty"] += (_num(h.get("qty")) or 0.0)
            c = _num(h.get("cost_basis"))
            if c is not None:
                slot["cost"] += c; slot["cost_avail"] = True
        holding_maps.append(hmap)
        per_snapshot.append({
            "snapshot_id": s.get("id"), "source": s.get("source"),
            "masked_account": _masked(s.get("account_ending")),
            "timestamp": _iso(s.get("created_at")),
            "recorded_value": _num(s.get("total_value")),
            "recorded_gain": _num(s.get("total_gain")),
            "positions": len(hmap),
        })

    transitions = []
    for i in range(1, len(snaps)):
        a, b = holding_maps[i - 1], holding_maps[i]
        av, bv = per_snapshot[i - 1]["recorded_value"], per_snapshot[i]["recorded_value"]
        new_pos = sorted(set(b) - set(a))
        closed = sorted(set(a) - set(b))
        qty_changes = []
        for k in sorted(set(a) & set(b)):
            dq = round(b[k]["qty"] - a[k]["qty"], 6)
            if dq:
                qty_changes.append({"symbol": k, "qty_change": dq,
                                    "from": round(a[k]["qty"], 6), "to": round(b[k]["qty"], 6)})
        val_change = (round(bv - av, 2) if (av is not None and bv is not None) else UNAVAILABLE)
        transitions.append({
            "from": per_snapshot[i - 1]["timestamp"], "to": per_snapshot[i]["timestamp"],
            "from_account": f"{per_snapshot[i-1]['source']} {per_snapshot[i-1]['masked_account']}",
            "to_account": f"{per_snapshot[i]['source']} {per_snapshot[i]['masked_account']}",
            "value_change": val_change,
            "value_change_pct": (round((bv - av) / av * 100, 2) if (av and bv is not None) else UNAVAILABLE),
            "new_positions": new_pos, "closed_positions": closed,
            "quantity_changes": qty_changes,
            "note": ("Deposits/withdrawals and price-vs-position attribution require per-holding "
                     "snapshot prices, which are not stored — reported as position + recorded-value "
                     "changes only."),
        })

    return {
        "mode": "compare",
        "base_currency": base_currency,
        "scope": scope_of(snaps),
        "per_snapshot": per_snapshot,
        "transitions": transitions,
        "data_quality": {
            "notes": ["Compare mode preserves each snapshot's recorded totals; per-holding prices "
                      "and deposits/withdrawals are not stored, so change attribution is limited to "
                      "positions and recorded values."],
            "price_timestamps": _price_timestamps(snaps),
        },
        "warnings": [],
    }


def analyze(snapshots: list[dict], mode: str = "consolidate",
            base_currency: str = "USD", enrich=None) -> dict:
    """Entry point. mode: 'consolidate' | 'compare'. Auto-suggest happens in the caller."""
    if (mode or "consolidate").lower() == "compare":
        return compare(snapshots, base_currency, enrich)
    return consolidate(snapshots, base_currency, enrich)


def suggest_mode(snapshots: list[dict]) -> str:
    """Unrelated accounts on the same date → consolidate. Multiple dates for one account
    → compare (historical)."""
    if detect_duplicate_accounts(snapshots):
        return "compare"
    return "consolidate"
