"""ArtikFinance import engine tests — period parsing/repair, classification, and a full
import of the real bundled workbook into an isolated DB (skipped if the workbook is absent)."""
import pytest

import finance


def test_parse_period_formats():
    assert finance.parse_period("Q1 2022") == (2022, 1)
    assert finance.parse_period("2018-Q3") == (2018, 3)
    assert finance.parse_period("2021 - Q4") == (2021, 4)
    assert finance.parse_period("2015") == (2015, None)
    assert finance.parse_period("2015.0") == (2015, None)
    assert finance.parse_period("Total") is None


def test_repair_periods_fixes_the_real_typo():
    # the actual header run from assets(2022 onward): ... Q2 2022, [Q3 2002], Q4 2022 ...
    hdrs = [(2021, 4), (2022, 1), (2022, 2), (2002, 3), (2022, 4), (2023, 1)]
    fixed = finance.repair_periods(hdrs)
    assert fixed[3] == (2022, 3)
    assert [p[0] for p in fixed] == [2021, 2022, 2022, 2022, 2022, 2023]  # no cascade


def test_repair_first_element_typo():
    assert finance.repair_periods([(1900, 1), (2020, 2)])[0] == (2020, 1)


def test_classification():
    assert finance.classify_asset("401K - Putnam") == ("401K", 0)
    assert finance.classify_asset("Schwab 1") == ("Brokerage", 1)
    assert finance.classify_asset("House 1") == ("Real Estate", 0)
    assert finance.classify_liability("House 2") == "Mortgage"
    assert finance.classify_liability("eTrade") == "Margin"
    assert finance.classify_liability("Arthy Wells (1/24-0%)") == "Credit Card"
    assert finance.classify_expense("NEWREZ-SHELLPOIN DES:ACH PMT") == "Housing"
    assert finance.classify_expense("CALWATER SERVICE") == "Utilities"


def test_aggregate_rows_detected():
    for name in ("Total", "Non House", "Debt (with house)", "401k", "Total Liquid"):
        assert finance.is_aggregate(name), name
    for name in ("401K - Putnam", "House 1", "Chase"):
        assert not finance.is_aggregate(name), name


@pytest.fixture()
def isolated_db(tmp_path):
    old = finance._DB_PATH
    finance._DB_PATH = tmp_path / "users.db"
    yield
    finance._DB_PATH = old


def test_full_import_real_workbook(isolated_db):
    pytest.importorskip("pandas")
    pytest.importorskip("openpyxl")
    if not finance.workbook_path():
        pytest.skip("bundled workbook not present")
    res = finance.run_import()
    assert res["ok"] and res["records"] > 1000 and res["tax_years"] > 10
    # merged continuous timeline, typo repaired, both eras present
    tl = finance.timeline("asset")
    years = {t["year"] for t in tl}
    assert min(years) == 2015 and max(years) >= 2025
    assert all(y >= 2010 for y in years)          # 'Q3 2002' repaired
    # net worth only on both-sided periods, positive current, aggregates not double counted
    nw = finance.net_worth()
    assert nw["stats"]["current"] > 0
    q4_21 = next(p for p in nw["points"] if p["period"] == "Q4 2021")
    assert q4_21["assets"] < 5_000_000            # was ~7M when era sheets double-counted
    # in-sheet duplicate items preserved distinctly
    items = {r["item"] for r in finance.records("liability")}
    assert "Chase" in items and "Chase #2" in items
    # summary + insights are computable
    s = finance.summary()
    assert s["net_worth"] and s["total_assets"] and len(s["insights"]) >= 3
