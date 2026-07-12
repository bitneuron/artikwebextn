"""ArtikFinance — Personal Financial Statement import engine + store + queries.

Imports the canonical workbook (artikAgents/agents/knowledge_bases/personal_financial_statement/
"Financial Statement.xlsx") into SQLite tables inside the users DB (Litestream→S3 on AWS, so the
imported data is durable). The workbook is ONLY used for importing; after import the database is
the authoritative runtime source. Import runs automatically at startup when no data exists, and
can be re-run (replace) via the admin API, with an import-history audit trail.

Parsing reality (inspected, not assumed):
- assets/liability sheets are MATRICES: col0 = item name, row0 = period headers ("2015",
  "Q1 2018", "2018-Q1", "Q4 2022"...). The two era sheets (2015-2021, 2022 onward) are merged
  into one continuous timeline; duplicate (item, period) cells prefer the newer sheet.
- Period headers contain typos (e.g. "Q3 2002" amid 2022 columns) — repaired against neighbors.
- Cashflow is a matrix of summary metrics over periods.
- Tax-Income is a proper table (header row = Year, Total Income, Wages, ...).
- Credit Card Interest is an APR reference table per card.
- Monthly_Expense_New holds three side-by-side (description, amount) column groups pasted from
  bank statements; lines are auto-categorized by keyword.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_DB_PATH = Path(os.environ.get("USERS_DB_PATH", str(_HERE / "config" / "users.db")))
_lock = threading.RLock()

# Workbook location: env override → Docker image copy → local repo (sibling submodule).
_XLSX_CANDIDATES = [
    os.environ.get("FINANCE_XLSX", ""),
    str(_HERE / "finance_kb" / "Financial Statement.xlsx"),
    str(_HERE.parent / "artikAgents" / "agents" / "knowledge_bases"
        / "personal_financial_statement" / "Financial Statement.xlsx"),
]


def workbook_path() -> str | None:
    for p in _XLSX_CANDIDATES:
        if p and Path(p).exists():
            return p
    return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(_DB_PATH), timeout=10, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=5000")
    return c


def init() -> None:
    with _conn() as c:
        # Schema migration: an early build keyed records by source_sheet too, which double-counts
        # periods present in both era sheets. Data is fully re-importable, so just rebuild.
        row = c.execute("SELECT sql FROM sqlite_master WHERE name='financial_records'").fetchone()
        if row and "source_sheet)" in re.sub(r"\s+", "", row["sql"] or ""):
            c.execute("DROP TABLE financial_records")
        c.executescript("""
        CREATE TABLE IF NOT EXISTS financial_records (
          id INTEGER PRIMARY KEY, dataset TEXT NOT NULL, item TEXT NOT NULL,
          category TEXT, liquid INTEGER, year INTEGER NOT NULL, quarter INTEGER,
          value REAL, is_total INTEGER DEFAULT 0, source_sheet TEXT,
          UNIQUE(dataset, item, year, quarter));
        CREATE INDEX IF NOT EXISTS ix_finrec ON financial_records(dataset, year, quarter);
        CREATE TABLE IF NOT EXISTS financial_tax_income (
          year INTEGER PRIMARY KEY, total_income REAL, wages REAL, capital_gain REAL,
          dividend REAL, interest REAL, tax_refund REAL, other_income REAL, extra TEXT);
        CREATE TABLE IF NOT EXISTS financial_cc_interest (
          card TEXT PRIMARY KEY, purchase_apr REAL, cash_advance_apr REAL,
          balance_transfer_apr REAL, note TEXT);
        CREATE TABLE IF NOT EXISTS financial_monthly_expenses (
          id INTEGER PRIMARY KEY, account_group TEXT, description TEXT,
          amount REAL, category TEXT);
        CREATE TABLE IF NOT EXISTS financial_import_history (
          id INTEGER PRIMARY KEY, ts TEXT, file TEXT, sheets INTEGER,
          rows INTEGER, status TEXT, detail TEXT);
        """)


# ── period + classification helpers ───────────────────────────────────────────
_QY = re.compile(r"^Q([1-4])\s*[- ]?\s*(\d{4})$")          # "Q1 2022"
_YQ = re.compile(r"^(\d{4})\s*[- ]?\s*Q([1-4])$")          # "2018-Q1"
_Y = re.compile(r"^(\d{4})(?:\.0)?$")                      # "2015" / 2015.0


def parse_period(raw) -> tuple[int, int | None] | None:
    s = str(raw).strip()
    m = _QY.match(s)
    if m:
        return (int(m.group(2)), int(m.group(1)))
    m = _YQ.match(s)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    m = _Y.match(s)
    if m and 1990 <= int(m.group(1)) <= 2100:
        return (int(m.group(1)), None)
    return None


def repair_periods(periods: list) -> list:
    """Fix header typos (e.g. 'Q3 2002' amid 2022 columns). Headers are chronological, so an
    element is a typo iff its year deviates >5 years from BOTH its valid neighbors (or its only
    neighbor at the ends). Neighbors are read from the ORIGINAL sequence so a single typo can
    never cascade into rewriting good columns. Snap to the previous neighbor (next, at the start)."""
    orig = list(periods)
    out = list(periods)
    idx = [i for i, p in enumerate(orig) if p]
    for pos, i in enumerate(idx):
        y, q = orig[i]
        prev_y = orig[idx[pos - 1]][0] if pos > 0 else None
        next_y = orig[idx[pos + 1]][0] if pos + 1 < len(idx) else None
        dev_prev = prev_y is not None and abs(y - prev_y) > 5
        dev_next = next_y is not None and abs(y - next_y) > 5
        neighbors = [d for d in (dev_prev if prev_y is not None else None,
                                 dev_next if next_y is not None else None) if d is not None]
        if neighbors and all(neighbors):
            out[i] = (prev_y if prev_y is not None else next_y, q)
    return out


# Aggregate/summary rows present inside the sheets (subtotals the owner keeps inline).
# They are stored (is_total=1) but excluded from computed sums to avoid double counting.
_AGGREGATE_ROWS = {
    "total", "asset", "401k", "529", "non 401k", "total liquid", "total non-liquid",
    "liability period", "total debt", "total debt (with house)", "credit card debt",
    "non house", "debt(non house-stock)", "debt (non house-stock)", "debt (stock margin)",
    "debt (with house)", "cashflow",
}


def is_aggregate(item: str) -> bool:
    low = re.sub(r"\s+", " ", (item or "").strip().lower())
    return low in _AGGREGATE_ROWS or "total" in low


_ASSET_RULES = [
    (r"401\s*k|putnam|fidelity|john", ("401K", 0)),
    (r"529|vanguard|alaska|t-?rowe", ("529", 0)),
    (r"propert|house|home|real\s*estate|rental", ("Real Estate", 0)),
    (r"coinbase|bit\s*coin|crypto|robinhood\s*crypto", ("Crypto", 1)),
    (r"marcus|cash|checking|saving|bofa|boa|chase bank|hysa|cd\b", ("Cash", 1)),
    (r"schwab|e\s*-?trade|etrade|ameritrade|robinhood|ibkr|interactive|broker|rsu|espp|stock",
     ("Brokerage", 1)),
]
_LIAB_RULES = [
    (r"mortgage|mortage|newrez|shellpoin|home\s*loan|^house", "Mortgage"),
    (r"margin|e\s*-?trade|etrade|charles|schwab|ameritrade|ibkr|interactive", "Margin"),
    (r"property\s*tax", "Property Tax"),
    (r"chase|amex|axp|american\s*express|wells|bofa|boa|citi|discover|amazon|credit|card", "Credit Card"),
    (r"loan|bmw|contractor|auto|car\b", "Loan"),
]


def classify_asset(item: str) -> tuple[str, int]:
    low = (item or "").lower()
    for pat, res in _ASSET_RULES:
        if re.search(pat, low):
            return res
    return ("Other", 1)


def classify_liability(item: str) -> str:
    low = (item or "").lower()
    for pat, res in _LIAB_RULES:
        if re.search(pat, low):
            return res
    return "Other Debt"


_EXPENSE_RULES = [
    (r"mortgage|mortage|newrez|shellpoin|rent|hoa", "Housing"),
    (r"water|calwater|pg&e|pge|edco|electric|gas\b|comcast|xfinity|at&t|att\b|adt|internet|phone|t-?mobile|verizon", "Utilities"),
    (r"insurance|pac-?life|geico|allstate|statefarm", "Insurance"),
    (r"safeway|costco|grocery|whole\s*foods|trader|restaurant|doordash|ubereats|instacart|food", "Food"),
    (r"medical|dental|kaiser|pharmacy|cvs|walgreens|health", "Medical"),
    (r"school|tuition|piano|chess|swim|robotics|class|college|eye\s*level", "Education"),
    (r"amazon|target|walmart|shopping|apple\.com|bestbuy", "Shopping"),
    (r"airline|united|delta|alaska\s*air|hotel|airbnb|travel|expedia", "Travel"),
    (r"529|vanguard|goldman|contrib|invest|coinbase|brokerage|401k|t-?rowe", "Investments"),
    (r"netflix|spotify|hulu|disney|youtube|prime\s*video|entertainment", "Entertainment"),
    (r"salary|direct\s*dep|payroll|visa\s*usa", "Income"),
]


def classify_expense(desc: str) -> str:
    low = (desc or "").lower()
    for pat, res in _EXPENSE_RULES:
        if re.search(pat, low):
            return res
    return "Miscellaneous"


# ── import engine ─────────────────────────────────────────────────────────────
def _matrix_rows(df, dataset: str, sheet: str) -> list[tuple]:
    """Parse a matrix sheet (col0 = item, row0 = period headers) into record tuples.

    Duplicate item names WITHIN a sheet (e.g. two separate 'Chase' cards) get a positional
    suffix ('Chase', 'Chase #2') so they don't collide — and since both era sheets list items
    in the same order, the suffixes align across sheets, letting the (dataset,item,year,quarter)
    unique key merge the eras with newer sheets winning on shared periods (e.g. Q4 2021)."""
    import pandas as pd
    periods = repair_periods([parse_period(v) for v in df.iloc[0, 1:]])
    rows = []
    seen: dict[str, int] = {}
    for r in range(1, len(df)):
        item = str(df.iloc[r, 0]).strip()
        if not item or item.lower() in ("nan", "none", ""):
            continue
        seen[item] = seen.get(item, 0) + 1
        if seen[item] > 1:
            item = f"{item} #{seen[item]}"
        is_total = 1 if is_aggregate(item) else 0
        if dataset == "asset":
            category, liquid = classify_asset(item)
        elif dataset == "liability":
            category, liquid = classify_liability(item), None
        else:
            category, liquid = None, None
        for ci, period in enumerate(periods, start=1):
            if not period or ci >= df.shape[1]:
                continue
            val = pd.to_numeric(df.iloc[r, ci], errors="coerce")
            if pd.isna(val):
                continue
            y, q = period
            rows.append((dataset, item, category, liquid, y, q, float(val), is_total, sheet))
    return rows


def run_import(path: str | None = None, replace: bool = True) -> dict:
    """Full import: workbook → normalized tables. Returns a summary; records import history."""
    import pandas as pd
    init()
    path = path or workbook_path()
    if not path:
        with _conn() as c:
            c.execute("INSERT INTO financial_import_history (ts, file, sheets, rows, status, detail) "
                      "VALUES (?,?,?,?,?,?)", (_now(), "(not found)", 0, 0, "failed", "workbook not found"))
        return {"ok": False, "error": "financial statement workbook not found"}

    xl = pd.ExcelFile(path)
    names = {n.lower().replace(" ", ""): n for n in xl.sheet_names}

    def sheet(prefix: str) -> list[str]:
        return [orig for key, orig in names.items() if key.startswith(prefix)]

    records: list[tuple] = []
    parsed_sheets = 0
    # Era order matters: older sheets first so newer sheets win on duplicate periods (INSERT OR REPLACE).
    for ds, prefix in (("asset", "assets(2015"), ("asset", "assets(2022"),
                       ("liability", "liability(2015"), ("liability", "liability(2022"),
                       ("cashflow", "cashflow")):
        for nm in sheet(prefix):
            records += _matrix_rows(xl.parse(nm, header=None), ds, nm)
            parsed_sheets += 1

    tax_rows, cc_rows, exp_rows = [], [], []
    for nm in sheet("tax-income"):
        df = xl.parse(nm)
        parsed_sheets += 1
        cols = {str(c).strip().lower(): c for c in df.columns}
        for _, r in df.iterrows():
            y = pd.to_numeric(r.get(cols.get("year")), errors="coerce")
            if pd.isna(y):
                continue
            def g(k):
                v = pd.to_numeric(r.get(cols.get(k)), errors="coerce")
                return None if pd.isna(v) else float(v)
            known = ("year", "total income", "wages", "capital gain", "dividend",
                     "interest", "tax refund", "other income")
            extra = {str(k): (None if pd.isna(v) else str(v)) for k, v in r.items()
                     if str(k).strip().lower() not in known and not pd.isna(v)}
            tax_rows.append((int(y), g("total income"), g("wages"), g("capital gain"),
                             g("dividend"), g("interest"), g("tax refund"), g("other income"),
                             json.dumps(extra)))
    for nm in sheet("creditcardinterest"):
        df = xl.parse(nm, header=None)
        parsed_sheets += 1
        for r in range(1, len(df)):
            card = str(df.iloc[r, 0]).strip()
            if not card or card.lower() == "nan":
                continue
            def num(ci):
                v = pd.to_numeric(df.iloc[r, ci], errors="coerce") if ci < df.shape[1] else None
                return None if v is None or pd.isna(v) else float(v)
            note = str(df.iloc[r, 4]).strip() if df.shape[1] > 4 and not pd.isna(df.iloc[r, 4]) else None
            cc_rows.append((card, num(1), num(2), num(3), note))
    for nm in sheet("monthly_expense_new"):
        df = xl.parse(nm, header=None)
        parsed_sheets += 1
        groups = [(0, 1), (3, 4), (6, 7)]   # (description col, amount col) side-by-side blocks
        for dcol, acol in groups:
            if acol >= df.shape[1]:
                continue
            gname = str(df.iloc[0, dcol]).strip() if not pd.isna(df.iloc[0, dcol]) else f"col{dcol}"
            for r in range(1, len(df)):
                desc = str(df.iloc[r, dcol]).strip()
                amt = pd.to_numeric(df.iloc[r, acol], errors="coerce")
                if not desc or desc.lower() == "nan" or pd.isna(amt):
                    continue
                exp_rows.append((gname, desc[:300], float(amt), classify_expense(desc)))

    with _lock, _conn() as c:
        if replace:
            for t in ("financial_records", "financial_tax_income",
                      "financial_cc_interest", "financial_monthly_expenses"):
                c.execute(f"DELETE FROM {t}")
        c.executemany("INSERT OR REPLACE INTO financial_records "
                      "(dataset,item,category,liquid,year,quarter,value,is_total,source_sheet) "
                      "VALUES (?,?,?,?,?,?,?,?,?)", records)
        c.executemany("INSERT OR REPLACE INTO financial_tax_income VALUES (?,?,?,?,?,?,?,?,?)", tax_rows)
        c.executemany("INSERT OR REPLACE INTO financial_cc_interest VALUES (?,?,?,?,?)", cc_rows)
        c.executemany("INSERT INTO financial_monthly_expenses (account_group,description,amount,category) "
                      "VALUES (?,?,?,?)", exp_rows)
        total = len(records) + len(tax_rows) + len(cc_rows) + len(exp_rows)
        c.execute("INSERT INTO financial_import_history (ts, file, sheets, rows, status, detail) "
                  "VALUES (?,?,?,?,?,?)",
                  (_now(), Path(path).name, parsed_sheets, total, "ok",
                   f"records={len(records)} tax={len(tax_rows)} cc={len(cc_rows)} expenses={len(exp_rows)}"))
    return {"ok": True, "file": Path(path).name, "sheets": parsed_sheets,
            "records": len(records), "tax_years": len(tax_rows),
            "cards": len(cc_rows), "expense_lines": len(exp_rows)}


def ensure_imported() -> None:
    """Startup hook: import the bundled workbook once, if the DB has no financial data."""
    try:
        init()
        with _conn() as c:
            n = c.execute("SELECT COUNT(*) FROM financial_records").fetchone()[0]
        if n == 0:
            res = run_import()
            print(f"[finance] startup import: {res}")
    except Exception as e:  # noqa: BLE001 — finance import must never block app startup
        print(f"[finance] startup import failed: {e}")


# ── queries (DB is the runtime source; Excel is never read after import) ─────
def _period_key(y: int, q: int | None) -> float:
    return y + ((q or 4) / 10.0)


def timeline(dataset: str) -> list[dict]:
    """Per-period totals for a dataset (excluding rows named 'total' to avoid double counting)."""
    with _conn() as c:
        rows = c.execute(
            "SELECT year, quarter, SUM(value) AS total FROM financial_records "
            "WHERE dataset=? AND is_total=0 GROUP BY year, quarter ORDER BY year, quarter",
            (dataset,)).fetchall()
    return [{"year": r["year"], "quarter": r["quarter"], "period":
             (f"Q{r['quarter']} {r['year']}" if r["quarter"] else str(r["year"])),
             "total": round(r["total"] or 0, 2)} for r in rows]


def records(dataset: str, year: int | None = None, quarter: int | None = None) -> list[dict]:
    q = ("SELECT item, category, liquid, year, quarter, value, is_total, source_sheet "
         "FROM financial_records WHERE dataset=?")
    args: list = [dataset]
    if year:
        q += " AND year=?"
        args.append(year)
    if quarter:
        q += " AND quarter=?"
        args.append(quarter)
    q += " ORDER BY year, quarter, item"
    with _conn() as c:
        return [dict(r) for r in c.execute(q, args).fetchall()]


def latest_breakdown(dataset: str) -> dict:
    """Latest period's per-item and per-category values."""
    tl = timeline(dataset)
    if not tl:
        return {"period": None, "items": [], "categories": {}, "total": 0}
    last = tl[-1]
    rows = [r for r in records(dataset, last["year"], last["quarter"]) if not r["is_total"]]
    cats: dict[str, float] = {}
    for r in rows:
        cats[r["category"] or "Other"] = cats.get(r["category"] or "Other", 0) + (r["value"] or 0)
    return {"period": last["period"], "year": last["year"], "quarter": last["quarter"],
            "total": last["total"], "items": rows,
            "categories": {k: round(v, 2) for k, v in sorted(cats.items(), key=lambda x: -x[1])}}


def net_worth() -> dict:
    a = {(t["year"], t["quarter"]): t for t in timeline("asset")}
    l = {(t["year"], t["quarter"]): t for t in timeline("liability")}
    pts = []
    # Only periods with BOTH sides recorded — an assets-only column would fake a net-worth spike.
    for key in sorted(set(a) & set(l), key=lambda k: _period_key(*k)):
        av = a.get(key, {}).get("total", 0)
        lv = l.get(key, {}).get("total", 0)
        pts.append({"year": key[0], "quarter": key[1],
                    "period": (f"Q{key[1]} {key[0]}" if key[1] else str(key[0])),
                    "assets": av, "liabilities": lv, "net_worth": round(av - lv, 2)})
    stats = {}
    if pts:
        nws = [p["net_worth"] for p in pts]
        first, last = pts[0], pts[-1]
        years = max(1e-9, _period_key(last["year"], last["quarter"]) - _period_key(first["year"], first["quarter"]))
        cagr = (((last["net_worth"] / first["net_worth"]) ** (1 / years)) - 1) * 100 \
            if first["net_worth"] and first["net_worth"] > 0 and last["net_worth"] > 0 else None
        stats = {"current": last["net_worth"], "period": last["period"],
                 "highest": max(nws), "lowest": min(nws),
                 "average": round(sum(nws) / len(nws), 2),
                 "cagr_pct": round(cagr, 2) if cagr is not None else None}
    return {"points": pts, "stats": stats}


def tax_income() -> list[dict]:
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM financial_tax_income ORDER BY year").fetchall()]


def cc_interest() -> list[dict]:
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM financial_cc_interest ORDER BY card").fetchall()]


def monthly_expenses() -> dict:
    with _conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT account_group, description, amount, category FROM financial_monthly_expenses "
            "ORDER BY amount").fetchall()]
    cats: dict[str, float] = {}
    for r in rows:
        if r["category"] != "Income" and (r["amount"] or 0) < 0:
            cats[r["category"]] = cats.get(r["category"], 0) + abs(r["amount"])
    income = sum(r["amount"] for r in rows if r["category"] == "Income" and (r["amount"] or 0) > 0)
    spend = sum(v for v in cats.values())
    return {"lines": rows, "categories": {k: round(v, 2) for k, v in sorted(cats.items(), key=lambda x: -x[1])},
            "monthly_income": round(income, 2), "monthly_spend": round(spend, 2)}


def import_history() -> list[dict]:
    init()
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM financial_import_history ORDER BY id DESC LIMIT 20").fetchall()]


def insights() -> list[str]:
    """Rule-based, data-derived insights for the dashboard (no fabrication — computed)."""
    out = []
    try:
        nw = net_worth()
        pts = nw["points"]
        if len(pts) >= 2:
            last = pts[-1]
            yr_ago = next((p for p in reversed(pts)
                           if _period_key(p["year"], p["quarter"])
                           <= _period_key(last["year"], last["quarter"]) - 1), pts[0])
            if yr_ago["net_worth"]:
                chg = (last["net_worth"] - yr_ago["net_worth"]) / abs(yr_ago["net_worth"]) * 100
                out.append(f"Net worth {'increased' if chg >= 0 else 'decreased'} "
                           f"{abs(chg):.0f}% year-over-year (now ${last['net_worth']:,.0f}).")
        a = latest_breakdown("asset")
        if a["total"]:
            liq = sum(r["value"] or 0 for r in a["items"] if r["liquid"])
            out.append(f"Liquid assets are ${liq:,.0f} ({liq / a['total'] * 100:.0f}% of total assets).")
            top = next(iter(a["categories"].items()), None)
            if top:
                out.append(f"{top[0]} is the largest asset class at "
                           f"{top[1] / a['total'] * 100:.0f}% of total assets.")
        lb = latest_breakdown("liability")
        mort = lb["categories"].get("Mortgage")
        if mort and a.get("total"):
            out.append(f"Mortgage balance is ${mort:,.0f}; total debt-to-asset ratio "
                       f"{lb['total'] / a['total'] * 100:.0f}%.")
        exp = monthly_expenses()
        topcat = next(iter(exp["categories"].items()), None)
        if topcat:
            out.append(f"Largest monthly spending category: {topcat[0]} (${topcat[1]:,.0f}).")
        if exp["monthly_income"] and exp["monthly_spend"]:
            rate = (exp["monthly_income"] - exp["monthly_spend"]) / exp["monthly_income"] * 100
            out.append(f"Approximate monthly savings rate: {rate:.0f}%.")
    except Exception as e:  # noqa: BLE001
        out.append(f"(insights unavailable: {e})")
    return out


def summary() -> dict:
    """Dashboard cards + insights."""
    a = latest_breakdown("asset")
    lb = latest_breakdown("liability")
    exp = monthly_expenses()
    nw = net_worth()
    liq = sum(r["value"] or 0 for r in a["items"] if r["liquid"])
    return {
        "as_of": a.get("period"),
        "net_worth": (nw["stats"] or {}).get("current"),
        "total_assets": a.get("total"),
        "total_liabilities": lb.get("total"),
        "liquid_assets": round(liq, 2),
        "brokerage": a["categories"].get("Brokerage"),
        "cash": a["categories"].get("Cash"),
        "monthly_income": exp["monthly_income"],
        "monthly_expenses": exp["monthly_spend"],
        "debt_to_asset_pct": round(lb["total"] / a["total"] * 100, 1) if a.get("total") else None,
        "asset_categories": a["categories"],
        "liability_categories": lb["categories"],
        "insights": insights(),
    }
