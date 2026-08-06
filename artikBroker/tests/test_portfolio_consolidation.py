"""Tests for the Multi-Snapshot Portfolio Analysis consolidation engine.

Covers the acceptance-criteria scenarios: consolidation, duplicate holdings, missing cost
basis, options, cash duplication, multiple currencies, historical comparison, and accidental
selection of multiple dates for one account.
"""
import portfolio_consolidation as pc

U = pc.UNAVAILABLE

# Deterministic price/metadata so market values are testable without live data.
PRICES = {"NVDA": 100.0, "AAPL": 200.0, "MSFT": 50.0, "TSM": 40.0, "AMD": 10.0}
NAMES = {"NVDA": "NVIDIA Corp", "AAPL": "Apple Inc"}


def enrich(tickers):
    return {t: {"price": PRICES[t], "name": NAMES.get(t, t), "sector": "Technology",
                "asset_class": "equity"} for t in tickers if t in PRICES}


def snap(sid, source, ending, holdings, total_value=None, total_gain=None, created="2026-08-02T17:37:00Z"):
    return {"id": sid, "source": source, "account_ending": ending,
            "label": f"{source} ••{ending}", "holdings": holdings,
            "total_value": total_value, "total_gain": total_gain, "created_at": created}


# ── consolidation across two brokerages ──────────────────────────────────────
def test_consolidate_two_sources():
    snaps = [
        snap("etrade_8524", "etrade", "8524", [{"ticker": "NVDA", "qty": 10, "cost_basis": 500},
                                               {"ticker": "AAPL", "qty": 5, "cost_basis": 800}], 2000),
        snap("schwab_7515", "schwab", "7515", [{"ticker": "MSFT", "qty": 20, "cost_basis": 900}], 1000),
    ]
    r = pc.consolidate(snaps, enrich=enrich)
    assert r["summary"]["n_snapshots"] == 2
    assert r["summary"]["n_accounts"] == 2
    assert r["summary"]["n_unique_securities"] == 3
    # combined market value = 10*100 + 5*200 + 20*50 = 3000
    assert r["summary"]["market_value"] == 3000.0
    # combined cost basis = 500+800+900 = 2200 (raw sum)
    assert r["summary"]["cost_basis"] == 2200.0
    # aggregate gain computed from dollars: 3000-2200 = 800
    assert r["summary"]["unrealized_gain"] == 800.0
    assert r["summary"]["unrealized_gain_pct"] == round(800 / 2200 * 100, 2)
    # each holding attributes its source/account
    nvda = next(h for h in r["holdings"] if h["symbol"] == "NVDA")
    assert nvda["sources"][0]["source"] == "etrade"
    assert nvda["sources"][0]["account"] == "••8524"


# ── duplicate holdings across accounts merge; qty == sum ─────────────────────
def test_duplicate_holding_merges_and_sums_quantity():
    snaps = [
        snap("etrade_8524", "etrade", "8524", [{"ticker": "NVDA", "qty": 10, "cost_basis": 500}], 1000),
        snap("schwab_7515", "schwab", "7515", [{"ticker": "NVDA", "qty": 7, "cost_basis": 700}], 700),
    ]
    r = pc.consolidate(snaps, enrich=enrich)
    assert r["summary"]["n_unique_securities"] == 1
    nvda = r["holdings"][0]
    assert nvda["symbol"] == "NVDA"
    assert nvda["qty"] == 17                         # 10 + 7
    assert nvda["cost_basis"] == 1200               # 500 + 700 raw
    assert nvda["market_value"] == 1700             # 17 * 100
    assert nvda["gain"] == 500                       # 1700 - 1200
    # appears in both accounts, flagged as duplicated
    assert len(nvda["sources"]) == 2
    assert any(d["symbol"] == "NVDA" for d in r["risks"]["duplicated_across_accounts"])


# ── missing cost basis → Unavailable, never zero ─────────────────────────────
def test_missing_cost_basis_is_unavailable_not_zero():
    snaps = [snap("etrade_8524", "etrade", "8524",
                  [{"ticker": "NVDA", "qty": 10, "cost_basis": 500},
                   {"ticker": "AAPL", "qty": 5, "cost_basis": None}], 2000)]
    r = pc.consolidate(snaps, enrich=enrich)
    aapl = next(h for h in r["holdings"] if h["symbol"] == "AAPL")
    assert aapl["cost_basis"] == U
    assert aapl["gain"] == U                          # cannot compute without cost
    assert aapl["market_value"] == 1000              # price still applies
    # aggregate cost excludes AAPL (not counted as 0): only NVDA's 500
    assert r["summary"]["cost_basis"] == 500
    assert "cost basis" in r["data_quality"]["missing_fields"]


# ── options kept separate by full contract symbol ────────────────────────────
def test_options_kept_separate():
    snaps = [snap("etrade_8524", "etrade", "8524", [
        {"ticker": "AAPL 260116C00190000", "qty": 1, "cost_basis": 300},
        {"ticker": "AAPL 260116P00190000", "qty": 1, "cost_basis": 200},
        {"ticker": "AAPL", "qty": 5, "cost_basis": 800},
    ], 1300)]
    r = pc.consolidate(snaps, enrich=enrich)
    syms = {h["symbol"] for h in r["holdings"]}
    # the call, the put, and the equity are three distinct securities
    assert "AAPL 260116C00190000" in syms
    assert "AAPL 260116P00190000" in syms
    assert "AAPL" in syms
    assert r["summary"]["n_unique_securities"] == 3
    call = next(h for h in r["holdings"] if h["symbol"] == "AAPL 260116C00190000")
    assert call["asset_type"] == "option"


# ── cash represented as a position is counted as cash, not a security ────────
def test_cash_not_double_counted_as_security():
    snaps = [snap("etrade_8524", "etrade", "8524", [
        {"ticker": "NVDA", "qty": 10, "cost_basis": 500},
        {"ticker": "SPAXX", "qty": 2500, "cost_basis": 2500},   # money-market cash position
        {"ticker": "CASH", "qty": 1000, "cost_basis": 1000},
    ], 4500)]
    r = pc.consolidate(snaps, enrich=enrich)
    # only NVDA is a security; cash rolls into the cash total
    assert r["summary"]["n_unique_securities"] == 1
    assert r["summary"]["cash"] == 3500              # 2500 + 1000
    # invested value excludes cash
    assert r["summary"]["invested_value"] == 1000    # NVDA 10*100
    assert not any(h["symbol"] in ("SPAXX", "CASH") for h in r["holdings"])


# ── multiple currencies: disclosed, base currency preserved ──────────────────
def test_multiple_currencies_disclosed():
    snaps = [snap("etrade_8524", "etrade", "8524", [{"ticker": "NVDA", "qty": 10, "cost_basis": 500}], 1000)]
    r = pc.consolidate(snaps, base_currency="EUR", enrich=enrich)
    assert r["base_currency"] == "EUR"
    assert r["summary"]["base_currency"] == "EUR"
    assert "currency" in r["data_quality"]["currency_note"].lower()


# ── historical comparison (Compare mode) ─────────────────────────────────────
def test_compare_mode_new_and_closed_and_qty_changes():
    snaps = [
        snap("etrade_0726", "etrade", "8524", [{"ticker": "NVDA", "qty": 10, "cost_basis": 500},
                                               {"ticker": "AAPL", "qty": 5, "cost_basis": 800}],
             2000, created="2026-07-26T17:00:00Z"),
        snap("etrade_0802", "etrade", "8524", [{"ticker": "NVDA", "qty": 15, "cost_basis": 800},
                                               {"ticker": "MSFT", "qty": 20, "cost_basis": 900}],
             3000, created="2026-08-02T17:00:00Z"),
    ]
    r = pc.compare(snaps, enrich=enrich)
    assert r["mode"] == "compare"
    t = r["transitions"][0]
    assert "MSFT" in t["new_positions"]
    assert "AAPL" in t["closed_positions"]
    assert t["value_change"] == 1000                 # 3000 - 2000 recorded
    nvda_change = next(c for c in t["quantity_changes"] if c["symbol"] == "NVDA")
    assert nvda_change["qty_change"] == 5             # 10 → 15


# ── accidental multiple dates for one account → double-count warning ─────────
def test_same_account_multiple_dates_warns_double_count():
    snaps = [
        snap("etrade_0726", "etrade", "8524", [{"ticker": "NVDA", "qty": 10, "cost_basis": 500}],
             1000, created="2026-07-26T17:00:00Z"),
        snap("etrade_0802", "etrade", "8524", [{"ticker": "NVDA", "qty": 15, "cost_basis": 800}],
             1500, created="2026-08-02T17:00:00Z"),
    ]
    dups = pc.detect_duplicate_accounts(snaps)
    assert dups and dups[0]["source"] == "etrade" and dups[0]["masked_account"] == "••8524"
    assert pc.suggest_mode(snaps) == "compare"
    r = pc.consolidate(snaps, enrich=enrich)
    assert any("DOUBLE-COUNT" in w for w in r["warnings"])


# ── reconciliation compares recorded vs computed ────────────────────────────
def test_reconciliation_reports_difference():
    # recorded total 900, but live value = 10*100 = 1000 → +100 drift disclosed
    snaps = [snap("etrade_8524", "etrade", "8524", [{"ticker": "NVDA", "qty": 10, "cost_basis": 500}], 900)]
    r = pc.consolidate(snaps, enrich=enrich)
    assert r["reconciliation"]["sum_recorded_value"] == 900
    assert r["reconciliation"]["consolidated_market_value"] == 1000
    assert r["reconciliation"]["difference"] == 100


# ── aggregate percentage from aggregate dollars, not averaged percentages ────
def test_aggregate_percentage_from_dollars():
    # Holding A: +100% (cost 100 → value 200); Holding B: 0% (cost 900 → value 900).
    # Averaging pcts would give 50%; correct aggregate = 100/1000 = 10%.
    snaps = [snap("etrade_8524", "etrade", "8524", [
        {"ticker": "AAPL", "qty": 1, "cost_basis": 100},    # 1*200 = 200, cost 100 → +100
        {"ticker": "MSFT", "qty": 18, "cost_basis": 900},   # 18*50 = 900, cost 900 → 0
    ], 1100)]
    r = pc.consolidate(snaps, enrich=enrich)
    assert r["summary"]["unrealized_gain"] == 100
    assert r["summary"]["unrealized_gain_pct"] == round(100 / 1000 * 100, 2)  # 10.0, not 50


# ── single-snapshot consolidation still produces a valid consolidated view ───
def test_single_snapshot_consolidates():
    snaps = [snap("etrade_8524", "etrade", "8524", [{"ticker": "NVDA", "qty": 10, "cost_basis": 500}], 1000)]
    r = pc.consolidate(snaps, enrich=enrich)
    assert r["summary"]["n_snapshots"] == 1
    assert r["summary"]["market_value"] == 1000
    assert not r["warnings"]


# ── recorded per-holding price/day-change used (point-in-time, not live) ──────
def test_recorded_prices_and_day_change_preferred():
    # holdings carry recorded market_value/price/day_change → engine must use them, no live enrich
    snaps = [snap("etrade_8524", "etrade", "8524", [
        {"ticker": "NVDA", "qty": 10, "cost_basis": 500, "price": 190.0,
         "market_value": 1900.0, "day_change": 25.0, "cusip": "67066G104"},
        {"ticker": "AAPL", "qty": 5, "cost_basis": 800, "price": 300.0,
         "market_value": 1500.0, "day_change": -10.0}], 3400)]
    # enrich returns wildly different LIVE prices — must be IGNORED in favor of recorded
    r = pc.consolidate(snaps, enrich=lambda t: {x: {"price": 999.0} for x in t})
    nvda = next(h for h in r["holdings"] if h["symbol"] == "NVDA")
    assert nvda["market_value"] == 1900.0        # recorded, not 10*999
    assert nvda["price"] == 190.0
    assert nvda["day_change"] == 25.0
    assert r["summary"]["market_value"] == 3400.0        # 1900 + 1500 recorded
    assert r["summary"]["day_change"] == 15.0            # 25 + (-10)
    assert r["data_quality"]["price_basis"] == "recorded"
    assert nvda["cusip"] == "67066G104"


def test_mixed_recorded_and_live_disclosed():
    snaps = [snap("etrade_8524", "etrade", "8524", [
        {"ticker": "NVDA", "qty": 10, "cost_basis": 500, "price": 190.0, "market_value": 1900.0},
        {"ticker": "AAPL", "qty": 5, "cost_basis": 800}], 2700)]   # AAPL has no recorded price
    r = pc.consolidate(snaps, enrich=lambda t: {x: {"price": 200.0} for x in t})
    aapl = next(h for h in r["holdings"] if h["symbol"] == "AAPL")
    assert aapl["market_value"] == 1000.0        # live fallback 5*200
    assert r["data_quality"]["price_basis"] == "mixed"
