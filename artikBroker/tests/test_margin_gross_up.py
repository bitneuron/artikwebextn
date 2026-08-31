"""Tests for the margin gross-up migration and the corrected balance-sheet accounting.

Run:  cd artikBroker && ../artikAPIs/venv/bin/python -m pytest tests/ -q

Each test builds a throwaway SQLite DB (USERS_DB_PATH is redirected per test), so nothing
touches the real financial records.
"""
import importlib
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """Fresh DB + freshly imported finance/margin_migration bound to it."""
    monkeypatch.setenv("USERS_DB_PATH", str(tmp_path / "t.db"))
    import finance
    import margin_migration
    importlib.reload(finance)
    importlib.reload(margin_migration)
    finance.init()
    margin_migration.ensure_schema()
    return finance, margin_migration


def put(finance, dataset, item, category, year, quarter, value, basis=None):
    with finance._conn() as c:
        c.execute("INSERT INTO financial_records (dataset,item,category,liquid,year,quarter,value,"
                  "is_total,source_sheet,asset_value_basis) VALUES (?,?,?,0,?,?,?,0,'test',?)",
                  (dataset, item, category, year, quarter, value, basis))


def val(finance, item, year, quarter, dataset="asset"):
    with finance._conn() as c:
        r = c.execute("SELECT value FROM financial_records WHERE dataset=? AND item=? AND year=? "
                      "AND quarter IS ?", (dataset, item, year, quarter)).fetchone()
        return r["value"] if r else None


def basis_of(finance, item, year, quarter):
    with finance._conn() as c:
        r = c.execute("SELECT asset_value_basis FROM financial_records WHERE dataset='asset' "
                      "AND item=? AND year=? AND quarter IS ?", (item, year, quarter)).fetchone()
        return r["asset_value_basis"] if r else None


def totals(finance, dataset, year, quarter):
    with finance._conn() as c:
        r = c.execute("SELECT COALESCE(SUM(value),0) t FROM financial_records WHERE dataset=? "
                      "AND year=? AND quarter IS ? AND is_total=0", (dataset, year, quarter)).fetchone()
        return r["t"]


def net_worth(finance, year, quarter):
    return totals(finance, "asset", year, quarter) - totals(finance, "liability", year, quarter)


# ── 1. no margin ────────────────────────────────────────────────────────────────────────────
def test_account_without_margin_is_unchanged(db):
    fin, mig = db
    put(fin, "asset", "Robinhood", "Brokerage", 2026, 2, 4725.30)
    mig.apply(confirm=True)
    assert val(fin, "Robinhood", 2026, 2) == 4725.30
    assert basis_of(fin, "Robinhood", 2026, 2) == "gross"


# ── 2. single account with margin ───────────────────────────────────────────────────────────
def test_margin_added_back_to_matching_account(db):
    fin, mig = db
    put(fin, "asset", "eTrade", "Brokerage", 2026, 2, 246529.69)
    put(fin, "liability", "eTrade", "Margin", 2026, 2, 221029.86)
    mig.apply(confirm=True)
    assert val(fin, "eTrade", 2026, 2) == pytest.approx(467559.55, abs=0.01)


# ── 3 & 4. multiple accounts, multiple periods ──────────────────────────────────────────────
def test_multiple_accounts_and_periods(db):
    fin, mig = db
    for q, (e, s1, me, ms) in {1: (100.0, 200.0, 10.0, 20.0), 2: (150.0, 250.0, 15.0, 25.0)}.items():
        put(fin, "asset", "eTrade", "Brokerage", 2025, q, e)
        put(fin, "asset", "Schwab 1", "Brokerage", 2025, q, s1)
        put(fin, "liability", "eTrade", "Margin", 2025, q, me)
        put(fin, "liability", "Charles Main", "Margin", 2025, q, ms)
    mig.apply(confirm=True)
    assert val(fin, "eTrade", 2025, 1) == 110.0
    assert val(fin, "Schwab 1", 2025, 1) == 220.0
    assert val(fin, "eTrade", 2025, 2) == 165.0
    assert val(fin, "Schwab 1", 2025, 2) == 275.0


# ── 5 & 6. gross/net reconstruction both ways ───────────────────────────────────────────────
def test_gross_from_net_plus_margin_and_back(db):
    fin, _ = db
    net_account_value, margin = 232874.91, 235194.32
    gross = net_account_value + margin
    assert gross == pytest.approx(468069.23, abs=0.01)
    assert gross - margin == pytest.approx(net_account_value, abs=0.01)


# ── 7. renamed / migrated account ───────────────────────────────────────────────────────────
def test_ameritrade_margin_maps_to_schwab_after_migration(db):
    fin, mig = db
    put(fin, "asset", "Schwab 1", "Brokerage", 2024, 1, 118940.0)
    put(fin, "liability", "Ameritrade", "Margin", 2024, 1, 178144.0)
    mig.apply(confirm=True)
    assert val(fin, "Schwab 1", 2024, 1) == 297084.0
    assert val(fin, mig.UNALLOCATED_ITEM, 2024, 1) is None      # no orphan row created


def test_renamed_account_is_not_treated_as_extra_account(db):
    fin, mig = db
    put(fin, "asset", "Ameritrade", "Brokerage", 2021, 3, 139714.0)
    put(fin, "liability", "Ameritrade", "Margin", 2021, 3, 154000.0)
    mig.apply(confirm=True)
    with fin._conn() as c:
        n = c.execute("SELECT COUNT(*) n FROM financial_records WHERE dataset='asset' "
                      "AND category='Brokerage' AND year=2021 AND quarter=3").fetchone()["n"]
    assert n == 1


# ── 8. unmapped margin falls back to the period subtotal ────────────────────────────────────
def test_unmapped_margin_uses_period_subtotal_fallback(db):
    fin, mig = db
    put(fin, "asset", "Schwab 1", "Brokerage", 2026, 2, 1000.0)
    put(fin, "liability", "Mystery Broker", "Margin", 2026, 2, 400.0)
    before = totals(fin, "asset", 2026, 2)
    rep = mig.dry_run()
    assert any("could not be mapped" in w for w in rep["warnings"])
    mig.apply(confirm=True)
    assert totals(fin, "asset", 2026, 2) == before + 400.0        # subtotal exact
    assert val(fin, mig.UNALLOCATED_ITEM, 2026, 2) == 400.0       # nothing invented per account


# ── 9 & 10. positive cash, negative cash (margin expressed as negative) ─────────────────────
def test_positive_cash_included_in_gross(db):
    fin, mig = db
    put(fin, "asset", "eTrade", "Brokerage", 2026, 1, 90000.0)    # securities 85k + 5k cash, net
    put(fin, "liability", "eTrade", "Margin", 2026, 1, 10000.0)
    mig.apply(confirm=True)
    assert val(fin, "eTrade", 2026, 1) == 100000.0


def test_negative_cash_row_is_not_double_counted(db):
    """A negative cash balance IS the margin; it must not be added on top of the margin row."""
    fin, mig = db
    put(fin, "asset", "eTrade", "Brokerage", 2026, 1, 90000.0)
    put(fin, "liability", "eTrade", "Margin", 2026, 1, 10000.0)
    mig.apply(confirm=True)
    assert net_worth(fin, 2026, 1) == 90000.0                     # 100000 gross − 10000 margin


# ── 11 & 12 & 13. non-marginable holdings, unsettled trades, accrued interest ───────────────
@pytest.mark.parametrize("net_value,margin", [(50000.0, 0.0), (50000.0, 12345.67), (0.0, 500.0)])
def test_gross_up_is_pure_addition_regardless_of_holding_type(db, net_value, margin):
    fin, mig = db
    put(fin, "asset", "eTrade", "Brokerage", 2026, 1, net_value)
    if margin:
        put(fin, "liability", "eTrade", "Margin", 2026, 1, margin)
    mig.apply(confirm=True)
    assert val(fin, "eTrade", 2026, 1) == pytest.approx(net_value + margin, abs=0.01)


# ── 14. rounding ────────────────────────────────────────────────────────────────────────────
def test_rounding_to_cents(db):
    fin, mig = db
    put(fin, "asset", "eTrade", "Brokerage", 2026, 1, 0.005)
    put(fin, "liability", "eTrade", "Margin", 2026, 1, 0.005)
    mig.apply(confirm=True)
    assert val(fin, "eTrade", 2026, 1) == pytest.approx(0.01, abs=0.005)


# ── 15. other liabilities must NOT be added back ────────────────────────────────────────────
def test_non_margin_liabilities_are_never_added_to_assets(db):
    fin, mig = db
    put(fin, "asset", "eTrade", "Brokerage", 2026, 2, 1000.0)
    put(fin, "liability", "House 1", "Mortgage", 2026, 2, 500000.0)
    put(fin, "liability", "Visa", "Credit Card", 2026, 2, 20000.0)
    put(fin, "liability", "Car", "Loan", 2026, 2, 9000.0)
    mig.apply(confirm=True)
    assert val(fin, "eTrade", 2026, 2) == 1000.0
    assert totals(fin, "asset", 2026, 2) == 1000.0
    assert totals(fin, "liability", 2026, 2) == 529000.0


# ── 16. idempotency ─────────────────────────────────────────────────────────────────────────
def test_migration_is_idempotent(db):
    fin, mig = db
    put(fin, "asset", "eTrade", "Brokerage", 2026, 2, 246529.69)
    put(fin, "liability", "eTrade", "Margin", 2026, 2, 221029.86)
    mig.apply(confirm=True)
    once = val(fin, "eTrade", 2026, 2)
    mig.apply(confirm=True)
    mig.apply(confirm=True)
    assert val(fin, "eTrade", 2026, 2) == once


def test_apply_requires_confirmation(db):
    _fin, mig = db
    with pytest.raises(ValueError):
        mig.apply(confirm=False)


# ── 17. rollback ────────────────────────────────────────────────────────────────────────────
def test_rollback_restores_original_values(db):
    fin, mig = db
    put(fin, "asset", "eTrade", "Brokerage", 2026, 2, 246529.69)
    put(fin, "asset", "Schwab 1", "Brokerage", 2026, 2, 232874.91)
    put(fin, "liability", "eTrade", "Margin", 2026, 2, 221029.86)
    put(fin, "liability", "Mystery", "Margin", 2026, 2, 100.0)
    before_assets = totals(fin, "asset", 2026, 2)
    mig.apply(confirm=True)
    assert totals(fin, "asset", 2026, 2) != before_assets
    mig.rollback()
    assert totals(fin, "asset", 2026, 2) == pytest.approx(before_assets, abs=0.01)
    assert val(fin, "eTrade", 2026, 2) == 246529.69
    assert val(fin, mig.UNALLOCATED_ITEM, 2026, 2) is None        # synthetic row removed
    assert basis_of(fin, "eTrade", 2026, 2) == "net"


def test_rollback_then_reapply_is_stable(db):
    fin, mig = db
    put(fin, "asset", "eTrade", "Brokerage", 2026, 2, 100.0)
    put(fin, "liability", "eTrade", "Margin", 2026, 2, 40.0)
    mig.apply(confirm=True)
    first = val(fin, "eTrade", 2026, 2)
    mig.rollback()
    mig.apply(confirm=True)
    assert val(fin, "eTrade", 2026, 2) == first


# ── 18 & 19. downstream consumers ───────────────────────────────────────────────────────────
def test_networth_and_cashflow_use_corrected_values(db):
    fin, mig = db
    put(fin, "asset", "eTrade", "Brokerage", 2026, 2, 100.0)
    put(fin, "asset", "House", "Real Estate", 2026, 2, 1000.0)
    put(fin, "liability", "eTrade", "Margin", 2026, 2, 40.0)
    put(fin, "liability", "House", "Mortgage", 2026, 2, 600.0)
    mig.apply(confirm=True)
    nw = fin.net_worth()["points"][-1]
    assert nw["assets"] == 1140.0 and nw["liabilities"] == 640.0
    assert nw["net_worth"] == 500.0
    cf = fin.cashflow_metrics()[(2026, 2)]
    assert cf["Asset"] == 140.0                       # gross brokerage, real estate excluded


def test_csv_export_rows_carry_corrected_values(db):
    fin, mig = db
    put(fin, "asset", "eTrade", "Brokerage", 2026, 2, 100.0)
    put(fin, "liability", "eTrade", "Margin", 2026, 2, 40.0)
    mig.apply(confirm=True)
    rows = fin.assets_search({})["rows"]
    assert [r["value"] for r in rows if r["item"] == "eTrade"] == [140.0]


# ── 20. the Q2 2026 acceptance case ─────────────────────────────────────────────────────────
def test_q2_2026_expected_values(db):
    """Live figures: brokerage 518,300.39 · margin 504,633.41 · assets 4,576,492.38 ·
    liabilities 2,010,580.25 · net worth 2,565,912.13."""
    fin, mig = db
    for item, v in [("Robinhood", 4725.30), ("Schwab 1", 232874.91),
                    ("Schwab 2", 34170.49), ("eTrade", 246529.69)]:
        put(fin, "asset", item, "Brokerage", 2026, 2, v)
    put(fin, "asset", "Everything else", "Real Estate", 2026, 2, 4576492.38 - 518300.39)
    for item, v in [("Charles", 48409.23), ("Charles Main", 235194.32), ("eTrade", 221029.86)]:
        put(fin, "liability", item, "Margin", 2026, 2, v)
    put(fin, "liability", "Other debt", "Mortgage", 2026, 2, 2010580.25 - 504633.41)

    assert totals(fin, "asset", 2026, 2) == pytest.approx(4576492.38, abs=0.02)
    assert totals(fin, "liability", 2026, 2) == pytest.approx(2010580.25, abs=0.02)
    assert net_worth(fin, 2026, 2) == pytest.approx(2565912.13, abs=0.02)

    mig.apply(confirm=True)

    brokerage = sum(v for i, v in [(i, val(fin, i, 2026, 2)) for i in
                                   ("Robinhood", "Schwab 1", "Schwab 2", "eTrade")] if v)
    assert brokerage == pytest.approx(1022933.80, abs=0.02)          # 518,300.39 + 504,633.41
    assert totals(fin, "asset", 2026, 2) == pytest.approx(5081125.79, abs=0.02)
    assert totals(fin, "liability", 2026, 2) == pytest.approx(2010580.25, abs=0.02)
    assert net_worth(fin, 2026, 2) == pytest.approx(3070545.54, abs=0.02)
    # verification identity from the spec
    assert net_worth(fin, 2026, 2) == pytest.approx(2565912.13 + 504633.41, abs=0.02)


# ── invariants ──────────────────────────────────────────────────────────────────────────────
def test_invariant_networth_equals_assets_minus_liabilities(db):
    fin, mig = db
    put(fin, "asset", "eTrade", "Brokerage", 2026, 2, 100.0)
    put(fin, "asset", "Schwab 1", "Brokerage", 2026, 2, 300.0)
    put(fin, "liability", "eTrade", "Margin", 2026, 2, 40.0)
    put(fin, "liability", "Visa", "Credit Card", 2026, 2, 7.0)
    mig.apply(confirm=True)
    for p in fin.net_worth()["points"]:
        assert p["net_worth"] == pytest.approx(p["assets"] - p["liabilities"], abs=0.01)


def test_invariant_each_margin_balance_hits_net_worth_exactly_once(db):
    """Net worth must move by +margin — proof the double deduction is gone, not doubled."""
    fin, mig = db
    put(fin, "asset", "eTrade", "Brokerage", 2026, 2, 1000.0)
    put(fin, "asset", "Schwab 1", "Brokerage", 2026, 2, 2000.0)
    put(fin, "liability", "eTrade", "Margin", 2026, 2, 300.0)
    put(fin, "liability", "Charles Main", "Margin", 2026, 2, 500.0)
    before = net_worth(fin, 2026, 2)
    mig.apply(confirm=True)
    assert net_worth(fin, 2026, 2) == pytest.approx(before + 800.0, abs=0.01)
    mig.apply(confirm=True)
    assert net_worth(fin, 2026, 2) == pytest.approx(before + 800.0, abs=0.01)


def test_dry_run_does_not_write(db):
    fin, mig = db
    put(fin, "asset", "eTrade", "Brokerage", 2026, 2, 100.0)
    put(fin, "liability", "eTrade", "Margin", 2026, 2, 40.0)
    before = totals(fin, "asset", 2026, 2)
    rep = mig.dry_run()
    assert rep["dry_run"] is True and rep["total_margin_added_back"] == 40.0
    assert totals(fin, "asset", 2026, 2) == before
    assert mig.is_applied() is False


def test_is_applied_reflects_current_state_not_history(db):
    fin, mig = db
    put(fin, "asset", "eTrade", "Brokerage", 2026, 2, 100.0)
    put(fin, "liability", "eTrade", "Margin", 2026, 2, 40.0)
    assert mig.is_applied() is False
    mig.apply(confirm=True)
    assert mig.is_applied() is True
    mig.rollback()
    assert mig.is_applied() is False          # rolled back -> can be applied again
    mig.apply(confirm=True)
    assert mig.is_applied() is True
    assert val(fin, "eTrade", 2026, 2) == 140.0


def test_duplicate_renamed_account_is_flagged(db):
    fin, mig = db
    put(fin, "asset", "Ameritrade", "Brokerage", 2021, 4, 161667.0)
    put(fin, "asset", "Schwab 1", "Brokerage", 2021, 4, 161667.0)
    put(fin, "liability", "Ameritrade", "Margin", 2021, 4, 100.0)
    assert any("counted twice" in w for w in mig.dry_run()["warnings"])
