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
        CREATE TABLE IF NOT EXISTS payment_apps (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL,
          icon TEXT, category TEXT, notes TEXT, last_reviewed TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS financial_screenshots (
          id INTEGER PRIMARY KEY, ts TEXT, app_id INTEGER, app_name TEXT, month TEXT,
          status TEXT, summary TEXT, lines_json TEXT, applied INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS payment_accounts (
          id INTEGER PRIMARY KEY, app_id INTEGER, institution TEXT, account_name TEXT,
          account_type TEXT, masked_account TEXT, currency TEXT DEFAULT 'USD',
          current_balance REAL, statement_balance REAL, available_credit REAL, credit_limit REAL,
          minimum_payment_due REAL, total_payment_due REAL, remaining_amount_due REAL,
          due_date TEXT, last_payment_amount REAL, last_payment_date TEXT,
          scheduled_payment_amount REAL, scheduled_payment_date TEXT, autopay_enabled INTEGER,
          interest_charged REAL, fees_charged REAL, payment_status TEXT,
          latest_statement_month TEXT, latest_import_id INTEGER, notes TEXT, tags TEXT,
          is_archived INTEGER DEFAULT 0, deleted_at TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS payment_monthly_history (
          id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL, statement_month TEXT NOT NULL,
          statement_start_date TEXT, statement_end_date TEXT, statement_close_date TEXT,
          statement_balance REAL, current_balance REAL, minimum_payment_due REAL,
          total_payment_due REAL, total_payments REAL DEFAULT 0, remaining_amount_due REAL,
          due_date TEXT, interest_charged REAL, fees_charged REAL, new_purchases REAL, credits REAL,
          payment_status TEXT, source_type TEXT, source_import_id INTEGER,
          is_archived INTEGER DEFAULT 0, version INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT);
        CREATE INDEX IF NOT EXISTS ix_payhist ON payment_monthly_history(account_id, statement_month);
        CREATE TABLE IF NOT EXISTS payment_transactions (
          id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL, history_id INTEGER,
          payment_date TEXT, amount REAL, payment_method TEXT, payment_status TEXT DEFAULT 'Posted',
          confirmation TEXT, notes TEXT, statement_month TEXT, source_type TEXT DEFAULT 'manual',
          source_import_id INTEGER, deleted_at TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS payment_audit_log (
          id INTEGER PRIMARY KEY, entity_type TEXT, entity_id INTEGER, action TEXT,
          field_name TEXT, old_value TEXT, new_value TEXT, source TEXT, actor TEXT, created_at TEXT);
        """)
        # Migration: expense lines gained month + source once screenshot imports arrived.
        # Workbook rows keep source='workbook'; screenshot-applied rows are 'screenshot'.
        _addcols(c, "financial_monthly_expenses", {"month": "TEXT", "source": "TEXT"})
        # Payment Apps v2: account identity + archive; screenshots gained statement fields,
        # confidence, dedup hash, and account/history links.
        _addcols(c, "payment_apps", {
            "institution": "TEXT", "account_type": "TEXT", "account_name": "TEXT",
            "masked_account": "TEXT", "display_order": "INTEGER", "is_archived": "INTEGER DEFAULT 0",
            "updated_at": "TEXT"})
        _addcols(c, "financial_screenshots", {
            "source_hash": "TEXT", "confidence": "REAL", "fields_json": "TEXT",
            "account_id": "INTEGER", "history_id": "INTEGER", "archived": "INTEGER DEFAULT 0"})


def _addcols(c, table: str, cols: dict) -> None:
    have = {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
    for name, decl in cols.items():
        if name not in have:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


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
    header_title = str(df.iloc[0, 0]).strip().lower()   # e.g. 'Cashflow' — sheets repeat it mid-sheet
    for r in range(1, len(df)):
        item = str(df.iloc[r, 0]).strip()
        if not item or item.lower() in ("nan", "none", ""):
            continue
        if header_title and item.lower() == header_title:   # repeated header row, not data
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
            for t in ("financial_tax_income", "financial_cc_interest"):
                c.execute(f"DELETE FROM {t}")
            # Preserve UI-edited cells for periods/items the workbook doesn't cover —
            # workbook values still win on shared (item, period) keys via INSERT OR REPLACE.
            c.execute("DELETE FROM financial_records WHERE COALESCE(source_sheet,'') != 'manual-edit'")
            # Preserve screenshot-imported expense lines — only workbook rows are replaced.
            c.execute("DELETE FROM financial_monthly_expenses WHERE source IS NULL OR source='workbook'")
        c.executemany("INSERT OR REPLACE INTO financial_records "
                      "(dataset,item,category,liquid,year,quarter,value,is_total,source_sheet) "
                      "VALUES (?,?,?,?,?,?,?,?,?)", records)
        c.executemany("INSERT OR REPLACE INTO financial_tax_income VALUES (?,?,?,?,?,?,?,?,?)", tax_rows)
        c.executemany("INSERT OR REPLACE INTO financial_cc_interest VALUES (?,?,?,?,?)", cc_rows)
        c.executemany("INSERT INTO financial_monthly_expenses (account_group,description,amount,category,source) "
                      "VALUES (?,?,?,?,'workbook')", exp_rows)
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


# ── Inline matrix editing (Assets / Liabilities pages) ───────────────────────
_EDITABLE_DATASETS = {"asset", "liability"}


def _edit_guard(dataset: str) -> None:
    if dataset not in _EDITABLE_DATASETS:
        raise ValueError("only asset and liability records are editable")


def records_batch(dataset: str, changes: list, actor: str = "") -> dict:
    """Apply reviewed cell edits: value → upsert (source_sheet='manual-edit'), empty → delete.
    Every change is audited with old + new value."""
    _edit_guard(dataset)
    init()
    applied = deleted = 0
    with _lock, _conn() as c:
        for ch in changes or []:
            item = str(ch.get("item") or "").strip()[:200]
            if not item:
                continue
            y = int(ch.get("year"))
            if not 1990 <= y <= 2100:
                raise ValueError(f"year out of range: {y}")
            q = ch.get("quarter")
            q = int(q) if q not in (None, "", "null") else None
            if q is not None and not 1 <= q <= 4:
                raise ValueError("quarter must be 1–4")
            plabel = f"{y}" + (f"-Q{q}" if q else "")
            old = c.execute("SELECT value FROM financial_records WHERE dataset=? AND item=? "
                            "AND year=? AND quarter IS ?", (dataset, item, y, q)).fetchone()
            oldv = old["value"] if old else None
            v = ch.get("value")
            if v in (None, ""):
                if old:
                    c.execute("DELETE FROM financial_records WHERE dataset=? AND item=? "
                              "AND year=? AND quarter IS ?", (dataset, item, y, q))
                    deleted += 1
                    _audit(c, "record", 0, "delete", field=f"{dataset}:{item} {plabel}",
                           old=oldv, new=None, source="matrix-edit", actor=actor)
                continue
            try:
                v = float(str(v).replace(",", "").replace("$", "").strip())
            except ValueError:
                raise ValueError(f"'{ch.get('value')}' is not a valid amount for {item} ({plabel})")
            if v == oldv:
                continue
            if dataset == "asset":
                category, liquid = classify_asset(item)
            else:
                category, liquid = classify_liability(item), None
            c.execute("INSERT OR REPLACE INTO financial_records "
                      "(dataset,item,category,liquid,year,quarter,value,is_total,source_sheet) "
                      "VALUES (?,?,?,?,?,?,?,?,'manual-edit')",
                      (dataset, item, category, liquid, y, q, v,
                       1 if is_aggregate(item) else 0))
            applied += 1
            _audit(c, "record", 0, "update" if old else "create", field=f"{dataset}:{item} {plabel}",
                   old=oldv, new=v, source="matrix-edit", actor=actor)
    return {"ok": True, "applied": applied, "deleted": deleted}


def record_item_rename(dataset: str, old: str, new: str, actor: str = "") -> dict:
    _edit_guard(dataset)
    old, new = (old or "").strip(), (new or "").strip()[:200]
    if not old or not new:
        raise ValueError("both the current and the new item name are required")
    init()
    with _lock, _conn() as c:
        if c.execute("SELECT 1 FROM financial_records WHERE dataset=? AND item=? LIMIT 1",
                     (dataset, new)).fetchone():
            raise ValueError(f"an item named '{new}' already exists")
        n = c.execute("UPDATE financial_records SET item=? WHERE dataset=? AND item=?",
                      (new, dataset, old)).rowcount
        if not n:
            raise ValueError(f"item '{old}' not found")
        _audit(c, "record", 0, "rename", field=dataset, old=old, new=new,
               source="matrix-edit", actor=actor)
    return {"ok": True, "renamed": n}


def record_item_delete(dataset: str, item: str, actor: str = "") -> dict:
    _edit_guard(dataset)
    item = (item or "").strip()
    init()
    with _lock, _conn() as c:
        n = c.execute("DELETE FROM financial_records WHERE dataset=? AND item=?",
                      (dataset, item)).rowcount
        if not n:
            raise ValueError(f"item '{item}' not found")
        _audit(c, "record", 0, "delete-item", field=dataset, old=item,
               new=f"{n} records removed", source="matrix-edit", actor=actor)
    return {"ok": True, "deleted": n}


def cashflow_series() -> dict:
    """Cashflow sheet = independent summary metrics per period (Asset, Liability with/without
    house, Totals). They are separate lines — NEVER summed across rows. Repeated-header
    artifacts and identical '#N' duplicate rows are dropped."""
    init()
    metrics: dict[str, dict] = {}
    for r in records("cashflow"):
        if r["item"].strip().lower() == "cashflow":     # repeated header parsed as data (legacy imports)
            continue
        metrics.setdefault(r["item"], {})[(r["year"], r["quarter"])] = r["value"]
    for name in [n for n in list(metrics) if re.search(r" #\d+$", n)]:
        base = re.sub(r" #\d+$", "", name)
        if base in metrics and metrics[base] == metrics[name]:
            del metrics[name]
    pk = lambda p: p[0] + ((p[1] or 4) / 10.0)          # noqa: E731
    label = lambda p: (f"Q{p[1]} {p[0]}" if p[1] else str(p[0]))  # noqa: E731
    periods = sorted({p for v in metrics.values() for p in v}, key=pk)

    def okey(n: str):
        ln = n.lower()
        return (0 if ln == "asset" else 2 if ln == "total" else 1, n)
    names = sorted(metrics, key=okey)
    series = [{"name": n, "category": None,
               "points": [{"period": label(p), "value": metrics[n].get(p)} for p in periods]}
              for n in names]
    rows = [{"item": n, "period": label(p), "year": p[0], "quarter": p[1], "value": metrics[n][p]}
            for n in names for p in periods if metrics[n].get(p) is not None]
    return {"periods": [label(p) for p in periods], "items": names, "series": series, "rows": rows}


def assets_search(params: dict, dataset: str = "asset") -> dict:
    """One filtering service for the Assets/Liabilities pages — summary cards, trend,
    composition, and table all come from the SAME filtered dataset so they can never disagree.
    Filters: period_type (all|year|quarter|custom), year, quarter, period_from/to
    (any format parse_period understands), categories (csv), items (csv)."""
    init()
    noun = "asset" if dataset == "asset" else "liability"
    grand_total = "Total Assets" if dataset == "asset" else "Total Debt"
    with _conn() as c:
        base = [dict(r) for r in c.execute(
            "SELECT item, category, year, quarter, value FROM financial_records "
            "WHERE dataset=? AND is_total=0 ORDER BY year, quarter, item", (dataset,)).fetchall()]
    for r in base:
        r["category"] = r["category"] or "Other"
    key = lambda y, q: y + ((q or 4) / 10.0)          # noqa: E731 — annual rows sort after Q3
    label = lambda y, q: (f"Q{q} {y}" if q else str(y))  # noqa: E731

    years = sorted({r["year"] for r in base})
    cats_all = sorted({r["category"] for r in base})
    items_all = sorted({(r["item"], r["category"]) for r in base})

    ptype = str(params.get("period_type") or "all").lower()
    rows = base
    if ptype == "year" and params.get("year"):
        y = int(params["year"])
        rows = [r for r in rows if r["year"] == y]
    elif ptype == "quarter" and params.get("year"):
        y = int(params["year"])
        qs = re.sub(r"\D", "", str(params.get("quarter") or "1")) or "1"
        q = int(qs)
        rows = [r for r in rows if r["year"] == y and r["quarter"] == q]
    elif ptype == "custom":
        pf = parse_period(str(params.get("period_from") or "").strip())
        pt = parse_period(str(params.get("period_to") or "").strip())
        if not pf or not pt:
            raise ValueError("could not parse the custom period range — use e.g. 2023-Q1 or Q1 2023")
        if key(*pf) > key(*pt):
            raise ValueError("start period is after end period")
        rows = [r for r in rows if key(pf[0], pf[1]) <= key(r["year"], r["quarter"]) <= key(pt[0], pt[1])]
    cats_sel = [s.strip() for s in str(params.get("categories") or "").split(",") if s.strip()]
    if cats_sel:
        low = {s.lower() for s in cats_sel}
        rows = [r for r in rows if r["category"].lower() in low]
    items_sel = [s.strip() for s in str(params.get("items") or "").split("|") if s.strip()]
    if items_sel:
        low = {s.lower() for s in items_sel}
        rows = [r for r in rows if r["item"].lower() in low]

    periods = sorted({(r["year"], r["quarter"]) for r in rows}, key=lambda p: key(*p))
    plabels = [label(*p) for p in periods]
    per_total = {p: round(sum(r["value"] or 0 for r in rows if (r["year"], r["quarter"]) == p), 2)
                 for p in periods}

    # Trend series: items → line per item; categories → line per category; else total only.
    # A Total line is added whenever more than one group is plotted.
    if items_sel:
        gfield, groups, total_name = "item", sorted({r["item"] for r in rows}), "Total Selected"
    elif cats_sel:
        gfield, groups, total_name = "category", sorted({r["category"] for r in rows}), grand_total
    else:
        gfield, groups, total_name = None, [], grand_total
    icat = dict(items_all)
    series = []
    for g in groups:
        pts = [{"period": label(*p), "value": round(sum(
            r["value"] or 0 for r in rows if (r["year"], r["quarter"]) == p and r[gfield] == g), 2)}
            for p in periods]
        series.append({"name": g, "category": (icat.get(g) if gfield == "item" else g), "points": pts})
    if not groups or len(groups) > 1:
        series.append({"name": total_name, "category": None,
                       "points": [{"period": label(*p), "value": per_total[p]} for p in periods]})

    # Summary + composition are a snapshot at the LATEST period inside the filtered range.
    latest = periods[-1] if periods else None
    cat_totals, item_totals, total = {}, {}, 0.0
    if latest:
        for r in rows:
            if (r["year"], r["quarter"]) == latest:
                v = r["value"] or 0
                total += v
                cat_totals[r["category"]] = cat_totals.get(r["category"], 0) + v
                item_totals[r["item"]] = item_totals.get(r["item"], 0) + v
    comp_src = item_totals if (items_sel or cats_sel) else cat_totals
    comp = [{"name": k, "value": round(v, 2), "pct": round(v / total * 100, 1) if total else 0,
             "category": (icat.get(k) if (items_sel or cats_sel) else k)}
            for k, v in sorted(comp_src.items(), key=lambda x: -x[1])]

    messages = []
    if not rows:
        want = " / ".join(filter(None, [", ".join(cats_sel), ", ".join(items_sel)]))
        when = (f"{params.get('quarter') or ''} {params.get('year') or ''}".strip()
                if ptype in ("year", "quarter") else
                f"{params.get('period_from')}–{params.get('period_to')}" if ptype == "custom" else "")
        messages.append(f"No {noun} records match the selected filters"
                        + (f" ({want}{' in ' + when if when else ''})" if want or when else "") + ".")

    return {
        "filters": {"available_years": years, "available_quarters": ["Q1", "Q2", "Q3", "Q4"],
                    "available_categories": cats_all,
                    "available_items": [{"item": i, "category": c0} for i, c0 in items_all],
                    "applied": {"period_type": ptype, "year": params.get("year") or None,
                                "quarter": params.get("quarter") or None,
                                "period_from": params.get("period_from") or None,
                                "period_to": params.get("period_to") or None,
                                "categories": cats_sel, "items": items_sel}},
        "summary": {"period": label(*latest) if latest else None,
                    "total_assets": round(total, 2),
                    "category_totals": {k: round(v, 2) for k, v in
                                        sorted(cat_totals.items(), key=lambda x: -x[1])}},
        "trend": {"periods": plabels, "series": series,
                  "label": (plabels[0] if len(plabels) == 1 else f"{plabels[0]}–{plabels[-1]}") if plabels else "—"},
        "composition": comp,
        "rows": [{"item": r["item"], "category": r["category"], "period": label(r["year"], r["quarter"]),
                  "year": r["year"], "quarter": r["quarter"], "value": r["value"]} for r in rows],
        "messages": messages,
        "total_rows_all": len(base),
        # legacy shape (timeline) kept for any other consumer of this endpoint
        "timeline": [{"year": p[0], "quarter": p[1], "period": label(*p), "total": per_total[p]} for p in periods],
    }


def tax_income() -> list[dict]:
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM financial_tax_income ORDER BY year").fetchall()]


def cc_interest() -> list[dict]:
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM financial_cc_interest ORDER BY card").fetchall()]


def monthly_expenses(month: str | None = None) -> dict:
    """Expense lines + aggregates. Default = the workbook baseline snapshot; pass month
    ('YYYY-MM') to view a screenshot-imported month. `months` lists importable views."""
    init()
    with _conn() as c:
        if month:
            rows = [dict(r) for r in c.execute(
                "SELECT account_group, description, amount, category, month FROM financial_monthly_expenses "
                "WHERE month=? ORDER BY amount", (month,)).fetchall()]
        else:
            rows = [dict(r) for r in c.execute(
                "SELECT account_group, description, amount, category, month FROM financial_monthly_expenses "
                "WHERE source IS NULL OR source='workbook' ORDER BY amount").fetchall()]
        months = [r[0] for r in c.execute(
            "SELECT DISTINCT month FROM financial_monthly_expenses "
            "WHERE month IS NOT NULL ORDER BY month DESC").fetchall()]
    cats: dict[str, float] = {}
    for r in rows:
        if r["category"] != "Income" and (r["amount"] or 0) < 0:
            cats[r["category"]] = cats.get(r["category"], 0) + abs(r["amount"])
    income = sum(r["amount"] for r in rows if r["category"] == "Income" and (r["amount"] or 0) > 0)
    spend = sum(v for v in cats.values())
    return {"lines": rows, "categories": {k: round(v, 2) for k, v in sorted(cats.items(), key=lambda x: -x[1])},
            "monthly_income": round(income, 2), "monthly_spend": round(spend, 2),
            "month": month, "months": months}


# ── Payment Apps registry + screenshot→expense imports ───────────────────────
def payment_apps(include_archived: bool = False) -> list[dict]:
    init()
    with _conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM payment_apps" + ("" if include_archived else " WHERE COALESCE(is_archived,0)=0")
            + " ORDER BY COALESCE(display_order, 9999), name COLLATE NOCASE").fetchall()]
    return rows


def payment_app_save(data: dict, app_id: int | None = None, actor: str = "") -> dict:
    name = (data.get("name") or "").strip()
    url = (data.get("url") or "").strip()
    if not name or not url:
        raise ValueError("name and url are required")
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    icon = (data.get("icon") or "💳").strip()[:8]
    category = (data.get("category") or "").strip()[:60]
    notes = (data.get("notes") or "").strip()[:500]
    institution = (data.get("institution") or "").strip()[:80]
    account_type = (data.get("account_type") or "").strip()[:60]
    account_name = (data.get("account_name") or "").strip()[:120]
    masked = _mask_account(data.get("masked_account"))
    with _lock, _conn() as c:
        if app_id:
            c.execute("UPDATE payment_apps SET name=?, url=?, icon=?, category=?, notes=?, "
                      "institution=?, account_type=?, account_name=?, masked_account=?, updated_at=? WHERE id=?",
                      (name, url, icon, category, notes, institution, account_type, account_name,
                       masked, _now(), app_id))
            _audit(c, "app", app_id, "update", actor=actor)
        else:
            cur = c.execute("INSERT INTO payment_apps (name,url,icon,category,notes,institution,"
                            "account_type,account_name,masked_account,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (name, url, icon, category, notes, institution, account_type,
                             account_name, masked, _now()))
            app_id = cur.lastrowid
            _audit(c, "app", app_id, "create", actor=actor)
        row = c.execute("SELECT * FROM payment_apps WHERE id=?", (app_id,)).fetchone()
    return dict(row)


def payment_app_delete(app_id: int, actor: str = "") -> None:
    with _lock, _conn() as c:
        c.execute("DELETE FROM payment_apps WHERE id=?", (app_id,))
        _audit(c, "app", app_id, "delete", actor=actor)


def payment_app_archive(app_id: int, on: bool = True, actor: str = "") -> None:
    """Archived apps disappear from the active view + block new imports, but keep all history."""
    with _lock, _conn() as c:
        c.execute("UPDATE payment_apps SET is_archived=?, updated_at=? WHERE id=?",
                  (1 if on else 0, _now(), app_id))
        _audit(c, "app", app_id, "archive" if on else "restore", actor=actor)


def payment_app_reviewed(app_id: int) -> None:
    with _lock, _conn() as c:
        c.execute("UPDATE payment_apps SET last_reviewed=? WHERE id=?", (_now(), app_id))


def screenshot_save(app_id: int | None, app_name: str, month: str | None, extraction: dict,
                    source_hash: str | None = None) -> int:
    """Persist a vision-extraction result (pending review; the image itself is never stored)."""
    init()
    fields = {k: v for k, v in extraction.items() if k not in ("lines", "summary") and v not in (None, "")}
    with _lock, _conn() as c:
        cur = c.execute(
            "INSERT INTO financial_screenshots (ts, app_id, app_name, month, status, summary, "
            "lines_json, source_hash, confidence, fields_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (_now(), app_id, (app_name or "")[:120], month, "extracted",
             (extraction.get("summary") or "")[:500], json.dumps(extraction.get("lines") or []),
             source_hash, extraction.get("confidence"), json.dumps(fields)))
        return cur.lastrowid


def screenshot_duplicate(source_hash: str) -> dict | None:
    """Duplicate-import guard: same image hash already analyzed (and not archived/deleted)."""
    init()
    with _conn() as c:
        r = c.execute("SELECT id, ts, app_name, month, status FROM financial_screenshots "
                      "WHERE source_hash=? AND COALESCE(archived,0)=0 ORDER BY id DESC LIMIT 1",
                      (source_hash,)).fetchone()
    return dict(r) if r else None


def screenshots(limit: int = 30, include_archived: bool = False) -> list[dict]:
    init()
    with _conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM financial_screenshots"
            + ("" if include_archived else " WHERE COALESCE(archived,0)=0")
            + " ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]
    for r in rows:
        try:
            r["lines"] = json.loads(r.pop("lines_json") or "[]")
        except Exception:  # noqa: BLE001
            r["lines"] = []
        try:
            r["fields"] = json.loads(r.pop("fields_json") or "{}")
        except Exception:  # noqa: BLE001
            r["fields"] = {}
    return rows


def screenshot_archive(sid: int, on: bool = True, actor: str = "") -> None:
    with _lock, _conn() as c:
        c.execute("UPDATE financial_screenshots SET archived=? WHERE id=?", (1 if on else 0, sid))
        _audit(c, "import", sid, "archive" if on else "restore", actor=actor)


def screenshot_delete(sid: int, actor: str = "") -> None:
    with _lock, _conn() as c:
        c.execute("DELETE FROM financial_screenshots WHERE id=?", (sid,))
        _audit(c, "import", sid, "delete", actor=actor)


# ══════════════════════════════════════════════════════════════════════════════
# Payment Accounts — consolidated balances/dues/payments across registered apps.
# Current state lives in payment_accounts; per-statement-month records live in
# payment_monthly_history (versioned, never silently overwritten); payments in
# payment_transactions (soft-deleted); every mutation lands in payment_audit_log.
# ══════════════════════════════════════════════════════════════════════════════
PAY_STATUSES = ["Paid", "Partially Paid", "Payment Due", "Due Soon", "Overdue",
                "No Payment Required", "Statement Not Available", "Needs Review"]
PAY_TXN_STATUSES = ["Scheduled", "Pending", "Posted", "Failed", "Cancelled"]

_ACCT_FIELDS = ["app_id", "institution", "account_name", "account_type", "masked_account",
                "currency", "current_balance", "statement_balance", "available_credit",
                "credit_limit", "minimum_payment_due", "total_payment_due", "remaining_amount_due",
                "due_date", "last_payment_amount", "last_payment_date", "scheduled_payment_amount",
                "scheduled_payment_date", "autopay_enabled", "interest_charged", "fees_charged",
                "payment_status", "latest_statement_month", "notes", "tags"]
_HIST_FIELDS = ["statement_month", "statement_start_date", "statement_end_date",
                "statement_close_date", "statement_balance", "current_balance",
                "minimum_payment_due", "total_payment_due", "remaining_amount_due", "due_date",
                "interest_charged", "fees_charged", "new_purchases", "credits", "payment_status"]
_NUM_RE = re.compile(r"^-?\d+(\.\d+)?$")


def _mask_account(v) -> str:
    """Only ever keep the last 4 digits of any account identifier."""
    digits = re.sub(r"\D", "", str(v or ""))
    return digits[-4:] if digits else ""


def _audit(c, entity_type: str, entity_id, action: str, field: str | None = None,
           old=None, new=None, source: str = "ui", actor: str = "") -> None:
    c.execute("INSERT INTO payment_audit_log (entity_type, entity_id, action, field_name, "
              "old_value, new_value, source, actor, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
              (entity_type, entity_id, action, field,
               None if old is None else str(old)[:300], None if new is None else str(new)[:300],
               source, actor or "admin", _now()))


def _audit_diff(c, entity_type: str, entity_id, before: dict, after: dict, fields: list[str],
                source: str = "ui", actor: str = "") -> None:
    for f in fields:
        if f in after and (before.get(f) != after.get(f)):
            _audit(c, entity_type, entity_id, "update", f, before.get(f), after.get(f), source, actor)


def compute_status(total_due, remaining, paid, due_date, needs_review: bool = False) -> str:
    """Spec status ladder: review → nothing owed → paid → partial → date-based urgency."""
    if needs_review:
        return "Needs Review"
    td = total_due if total_due is not None else None
    if td is None:
        return "Statement Not Available"
    if td <= 0:
        return "No Payment Required"
    paid = paid or 0
    rem = remaining if remaining is not None else max(td - paid, 0)
    if paid >= td or rem <= 0:
        return "Paid"
    if paid > 0:
        return "Partially Paid"
    if due_date:
        try:
            days = (datetime.strptime(str(due_date)[:10], "%Y-%m-%d").date()
                    - datetime.now(timezone.utc).date()).days
            if days < 0:
                return "Overdue"
            if days <= 5:
                return "Due Soon"
        except ValueError:
            pass
    return "Payment Due"


def _num(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        raise ValueError(f"not a number: {v!r}")


def _acct_clean(data: dict) -> dict:
    """Whitelisted, validated account fields (mass-assignment guard)."""
    out = {}
    for f in _ACCT_FIELDS:
        if f not in data:
            continue
        v = data[f]
        if f in ("current_balance", "statement_balance", "available_credit", "credit_limit",
                 "minimum_payment_due", "total_payment_due", "remaining_amount_due",
                 "last_payment_amount", "scheduled_payment_amount", "interest_charged", "fees_charged"):
            v = _num(v)
        elif f == "masked_account":
            v = _mask_account(v)
        elif f == "autopay_enabled":
            v = 1 if v in (1, True, "1", "true", "yes") else 0
        elif f in ("due_date", "last_payment_date", "scheduled_payment_date") and v:
            if not re.match(r"^\d{4}-\d{2}-\d{2}", str(v)):
                raise ValueError(f"{f} must be YYYY-MM-DD")
            v = str(v)[:10]
        elif f == "latest_statement_month" and v:
            if not re.match(r"^\d{4}-\d{2}$", str(v)):
                raise ValueError("statement month must be YYYY-MM")
        elif f == "payment_status" and v and v not in PAY_STATUSES:
            v = None
        elif isinstance(v, str):
            v = v.strip()[:300]
        out[f] = v
    return out


def _recalc_history(c, hid: int) -> None:
    """total_payments = posted transactions for the row's month; then remaining + status.
    Payments attach to the (account, statement month), not a specific record version —
    a re-imported v2 statement must still see payments recorded against v1."""
    h = c.execute("SELECT * FROM payment_monthly_history WHERE id=?", (hid,)).fetchone()
    if not h:
        return
    paid = c.execute("SELECT COALESCE(SUM(amount),0) FROM payment_transactions "
                     "WHERE account_id=? AND payment_status='Posted' AND deleted_at IS NULL "
                     "AND (statement_month=? OR (statement_month IS NULL AND history_id=?))",
                     (h["account_id"], h["statement_month"], hid)).fetchone()[0]
    td = h["total_payment_due"]
    rem = max((td or 0) - paid, 0) if td is not None else None
    status = compute_status(td, rem, paid, h["due_date"],
                            needs_review=(h["payment_status"] == "Needs Review" and paid == 0))
    c.execute("UPDATE payment_monthly_history SET total_payments=?, remaining_amount_due=?, "
              "payment_status=?, updated_at=? WHERE id=?", (paid, rem, status, _now(), hid))


def _latest_history(c, account_id: int):
    return c.execute("SELECT * FROM payment_monthly_history WHERE account_id=? AND is_archived=0 "
                     "ORDER BY statement_month DESC, version DESC LIMIT 1", (account_id,)).fetchone()


def _refresh_summary(c, account_id: int) -> None:
    """Sync the current-account summary from its latest monthly record + payments."""
    h = _latest_history(c, account_id)
    lastpay = c.execute("SELECT amount, payment_date FROM payment_transactions "
                        "WHERE account_id=? AND payment_status='Posted' AND deleted_at IS NULL "
                        "ORDER BY payment_date DESC, id DESC LIMIT 1", (account_id,)).fetchone()
    sets, args = ["updated_at=?"], [_now()]
    if h:
        for src, dst in (("statement_balance", "statement_balance"), ("current_balance", "current_balance"),
                         ("minimum_payment_due", "minimum_payment_due"), ("total_payment_due", "total_payment_due"),
                         ("remaining_amount_due", "remaining_amount_due"), ("due_date", "due_date"),
                         ("interest_charged", "interest_charged"), ("fees_charged", "fees_charged"),
                         ("payment_status", "payment_status"), ("statement_month", "latest_statement_month"),
                         ("source_import_id", "latest_import_id")):
            if h[src] is not None:
                sets.append(f"{dst}=?")
                args.append(h[src])
    if lastpay:
        sets += ["last_payment_amount=?", "last_payment_date=?"]
        args += [lastpay["amount"], lastpay["payment_date"]]
    args.append(account_id)
    c.execute(f"UPDATE payment_accounts SET {', '.join(sets)} WHERE id=?", args)


def accounts_list(tab: str = "active") -> dict:
    """Consolidated view (one row per account) + portfolio metrics for the summary cards."""
    init()
    where = {"active": "a.deleted_at IS NULL AND a.is_archived=0",
             "archived": "a.deleted_at IS NULL AND a.is_archived=1",
             "trash": "a.deleted_at IS NOT NULL"}.get(tab, "a.deleted_at IS NULL AND a.is_archived=0")
    with _conn() as c:
        rows = [dict(r) for r in c.execute(
            f"SELECT a.*, p.name AS app_name, p.icon AS app_icon, p.url AS app_url, "
            f"(SELECT h.total_payments FROM payment_monthly_history h WHERE h.account_id=a.id "
            f" AND h.is_archived=0 ORDER BY h.statement_month DESC, h.version DESC LIMIT 1) AS total_payments "
            f"FROM payment_accounts a LEFT JOIN payment_apps p ON p.id=a.app_id "
            f"WHERE {where} ORDER BY a.due_date IS NULL, a.due_date, a.institution").fetchall()]
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        act = [dict(r) for r in c.execute(
            "SELECT * FROM payment_accounts WHERE deleted_at IS NULL AND is_archived=0").fetchall()]
        paid_month = c.execute(
            "SELECT COALESCE(SUM(t.amount),0) FROM payment_transactions t "
            "JOIN payment_accounts a ON a.id=t.account_id "
            "WHERE t.payment_status='Posted' AND t.deleted_at IS NULL AND a.deleted_at IS NULL "
            "AND substr(t.payment_date,1,7)=?", (month,)).fetchone()[0]
        interest_month = c.execute(
            "SELECT COALESCE(SUM(h.interest_charged),0) FROM payment_monthly_history h "
            "JOIN payment_accounts a ON a.id=h.account_id "
            "WHERE h.is_archived=0 AND a.deleted_at IS NULL AND h.statement_month=?",
            (month,)).fetchone()[0]
    due_month = sum((a["total_payment_due"] or 0) for a in act
                    if (a["due_date"] or "").startswith(month))
    metrics = {
        "month": month,
        "total_current_balance": round(sum(a["current_balance"] or 0 for a in act), 2),
        "total_due_this_month": round(due_month, 2),
        "paid_this_month": round(paid_month or 0, 2),
        "remaining_due": round(sum(a["remaining_amount_due"] or 0 for a in act), 2),
        "interest_this_month": round(interest_month or 0, 2),
        "due_soon": sum(1 for a in act if a["payment_status"] == "Due Soon"),
        "overdue": sum(1 for a in act if a["payment_status"] == "Overdue"),
    }
    return {"accounts": rows, "metrics": metrics, "tab": tab, "statuses": PAY_STATUSES}


def history_list(archived: bool | None = None, month: str | None = None) -> list[dict]:
    """All monthly statement records across accounts (History tab → Statements/Archived)."""
    init()
    q = ("SELECT h.*, a.account_name, a.app_id, a.institution, a.masked_account, p.name AS app_name "
         "FROM payment_monthly_history h JOIN payment_accounts a ON a.id=h.account_id "
         "LEFT JOIN payment_apps p ON p.id=a.app_id WHERE a.deleted_at IS NULL")
    args: list = []
    if archived is not None:
        q += " AND h.is_archived=?"
        args.append(1 if archived else 0)
    if month:
        q += " AND h.statement_month=?"
        args.append(month)
    q += " ORDER BY h.statement_month DESC, h.version DESC, h.account_id"
    with _conn() as c:
        return [dict(r) for r in c.execute(q, args).fetchall()]


def account_get(aid: int) -> dict:
    """Full detail for the drawer: summary + history + payments + imports + audit + linked expenses."""
    init()
    with _conn() as c:
        a = c.execute("SELECT a.*, p.name AS app_name, p.icon AS app_icon, p.url AS app_url "
                      "FROM payment_accounts a LEFT JOIN payment_apps p ON p.id=a.app_id "
                      "WHERE a.id=?", (aid,)).fetchone()
        if not a:
            raise ValueError("account not found")
        a = dict(a)
        hist = [dict(r) for r in c.execute(
            "SELECT * FROM payment_monthly_history WHERE account_id=? "
            "ORDER BY statement_month DESC, version DESC", (aid,)).fetchall()]
        pays = [dict(r) for r in c.execute(
            "SELECT * FROM payment_transactions WHERE account_id=? AND deleted_at IS NULL "
            "ORDER BY payment_date DESC, id DESC", (aid,)).fetchall()]
        imps = [dict(r) for r in c.execute(
            "SELECT id, ts, app_name, month, status, summary, confidence, applied, archived "
            "FROM financial_screenshots WHERE account_id=? ORDER BY id DESC", (aid,)).fetchall()]
        audit = [dict(r) for r in c.execute(
            "SELECT * FROM payment_audit_log WHERE (entity_type='account' AND entity_id=?) "
            "OR (entity_type='history' AND entity_id IN (SELECT id FROM payment_monthly_history WHERE account_id=?)) "
            "OR (entity_type='payment' AND entity_id IN (SELECT id FROM payment_transactions WHERE account_id=?)) "
            "ORDER BY id DESC LIMIT 200", (aid, aid, aid)).fetchall()]
        names = tuple({n for n in (a.get("app_name"), a.get("account_name")) if n})
        exp = []
        if names:
            q = ",".join("?" * len(names))
            exp = [dict(r) for r in c.execute(
                f"SELECT id, account_group, description, amount, category, month "
                f"FROM financial_monthly_expenses WHERE source='screenshot' AND account_group IN ({q}) "
                f"ORDER BY month DESC, id", names).fetchall()]
    return {"account": a, "history": hist, "payments": pays, "imports": imps,
            "audit": audit, "expenses": exp, "statuses": PAY_STATUSES, "txn_statuses": PAY_TXN_STATUSES}


def account_create(data: dict, actor: str = "", source: str = "ui") -> dict:
    fields = _acct_clean(data)
    if not (fields.get("account_name") or fields.get("institution")):
        raise ValueError("account_name or institution is required")
    cols = list(fields) + ["created_at", "updated_at"]
    vals = [fields[f] for f in fields] + [_now(), _now()]
    with _lock, _conn() as c:
        cur = c.execute(f"INSERT INTO payment_accounts ({','.join(cols)}) "
                        f"VALUES ({','.join('?' * len(cols))})", vals)
        aid = cur.lastrowid
        _audit(c, "account", aid, "create", source=source, actor=actor)
        # Optional inline first statement record (manual "+ Add Account Record" path).
        if data.get("statement_month"):
            _history_write(c, aid, data.get("statement_month"), {
                k: fields.get(k) for k in ("statement_balance", "current_balance",
                                           "minimum_payment_due", "total_payment_due", "due_date",
                                           "interest_charged", "fees_charged")},
                source_type="manual", actor=actor)
        _refresh_summary(c, aid)
        row = c.execute("SELECT * FROM payment_accounts WHERE id=?", (aid,)).fetchone()
    return dict(row)


def account_update(aid: int, data: dict, actor: str = "") -> dict:
    fields = _acct_clean(data)
    with _lock, _conn() as c:
        before = c.execute("SELECT * FROM payment_accounts WHERE id=?", (aid,)).fetchone()
        if not before:
            raise ValueError("account not found")
        before = dict(before)
        if before["is_archived"] and not set(fields) <= {"notes", "tags"}:
            raise ValueError("archived accounts are read-only (except notes/tags) — restore first")
        if not fields:
            return before
        sets = ", ".join(f"{f}=?" for f in fields) + ", updated_at=?"
        c.execute(f"UPDATE payment_accounts SET {sets} WHERE id=?",
                  list(fields.values()) + [_now(), aid])
        _audit_diff(c, "account", aid, before, fields, list(fields), actor=actor)
        # Manual balance/due edits re-derive status unless the user set one explicitly.
        if not fields.get("payment_status") and {"total_payment_due", "remaining_amount_due", "due_date"} & set(fields):
            row = c.execute("SELECT * FROM payment_accounts WHERE id=?", (aid,)).fetchone()
            c.execute("UPDATE payment_accounts SET payment_status=? WHERE id=?",
                      (compute_status(row["total_payment_due"], row["remaining_amount_due"],
                                      None, row["due_date"]), aid))
        row = c.execute("SELECT * FROM payment_accounts WHERE id=?", (aid,)).fetchone()
    return dict(row)


def account_archive(aid: int, on: bool = True, actor: str = "") -> None:
    with _lock, _conn() as c:
        c.execute("UPDATE payment_accounts SET is_archived=?, updated_at=? WHERE id=?",
                  (1 if on else 0, _now(), aid))
        _audit(c, "account", aid, "archive" if on else "restore", actor=actor)


def account_trash(aid: int, restore: bool = False, actor: str = "") -> None:
    """Soft delete → Trash tab; restore brings it back. Hard delete only from Trash."""
    with _lock, _conn() as c:
        c.execute("UPDATE payment_accounts SET deleted_at=?, updated_at=? WHERE id=?",
                  (None if restore else _now(), _now(), aid))
        _audit(c, "account", aid, "restore" if restore else "trash", actor=actor)


def account_purge(aid: int, actor: str = "") -> None:
    with _lock, _conn() as c:
        row = c.execute("SELECT deleted_at FROM payment_accounts WHERE id=?", (aid,)).fetchone()
        if not row:
            raise ValueError("account not found")
        if not row["deleted_at"]:
            raise ValueError("only trashed accounts can be permanently deleted")
        c.execute("DELETE FROM payment_transactions WHERE account_id=?", (aid,))
        c.execute("DELETE FROM payment_monthly_history WHERE account_id=?", (aid,))
        c.execute("DELETE FROM payment_accounts WHERE id=?", (aid,))
        _audit(c, "account", aid, "purge", actor=actor)


def _hist_clean(data: dict) -> dict:
    out = {}
    for f in _HIST_FIELDS + ["total_payments"]:
        if f not in data:
            continue
        v = data[f]
        if f == "statement_month":
            if v and not re.match(r"^\d{4}-\d{2}$", str(v)):
                raise ValueError("statement_month must be YYYY-MM")
        elif f in ("statement_start_date", "statement_end_date", "statement_close_date", "due_date"):
            if v and not re.match(r"^\d{4}-\d{2}-\d{2}", str(v)):
                raise ValueError(f"{f} must be YYYY-MM-DD")
            v = str(v)[:10] if v else None
        elif f == "payment_status":
            if v and v not in PAY_STATUSES:
                v = None
        else:
            v = _num(v)
        out[f] = v
    return out


def _history_write(c, account_id: int, month: str, fields: dict, source_type: str,
                   import_id: int | None = None, resolution: str | None = None,
                   actor: str = "") -> tuple[int, dict | None]:
    """Create/refresh the (account, month) record. If one exists and no resolution was chosen,
    return a conflict diff instead of writing — the user decides merge/replace/new-version."""
    fields = {k: v for k, v in fields.items() if k in _HIST_FIELDS and k != "statement_month"}
    existing = c.execute(
        "SELECT * FROM payment_monthly_history WHERE account_id=? AND statement_month=? "
        "AND is_archived=0 ORDER BY version DESC LIMIT 1", (account_id, month)).fetchone()
    if existing and not resolution:
        ex = dict(existing)
        diff = {k: {"existing": ex.get(k), "new": v} for k, v in fields.items()
                if v is not None and ex.get(k) != v}
        return existing["id"], {"conflict": True, "existing_id": existing["id"],
                                "existing_version": ex.get("version") or 1, "diff": diff}
    if existing and resolution in ("replace", "merge"):
        ex = dict(existing)
        if resolution == "merge":            # fill gaps only — existing values win
            fields = {k: v for k, v in fields.items() if v is not None and ex.get(k) is None}
        else:
            fields = {k: v for k, v in fields.items() if v is not None}
        if fields:
            sets = ", ".join(f"{f}=?" for f in fields)
            c.execute(f"UPDATE payment_monthly_history SET {sets}, source_type=?, "
                      f"source_import_id=COALESCE(?, source_import_id), updated_at=? WHERE id=?",
                      list(fields.values()) + [source_type, import_id, _now(), existing["id"]])
            _audit_diff(c, "history", existing["id"], ex, fields, list(fields),
                        source=source_type, actor=actor)
        hid = existing["id"]
    else:                                    # brand new month, or resolution == 'new_version'
        version = (existing["version"] + 1) if existing else 1
        cols = {k: v for k, v in fields.items() if v is not None}
        base = {"account_id": account_id, "statement_month": month, "version": version,
                "source_type": source_type, "source_import_id": import_id,
                "created_at": _now(), "updated_at": _now(), **cols}
        cur = c.execute(f"INSERT INTO payment_monthly_history ({','.join(base)}) "
                        f"VALUES ({','.join('?' * len(base))})", list(base.values()))
        hid = cur.lastrowid
        _audit(c, "history", hid, "create", field="version", new=version,
               source=source_type, actor=actor)
    _recalc_history(c, hid)
    return hid, None


def history_update(hid: int, data: dict, actor: str = "") -> dict:
    fields = _hist_clean(data)
    fields.pop("statement_month", None)      # the month key is immutable; add a new record instead
    with _lock, _conn() as c:
        before = c.execute("SELECT * FROM payment_monthly_history WHERE id=?", (hid,)).fetchone()
        if not before:
            raise ValueError("history record not found")
        before = dict(before)
        if before["is_archived"]:
            raise ValueError("archived records are read-only — restore first")
        if fields:
            sets = ", ".join(f"{f}=?" for f in fields)
            c.execute(f"UPDATE payment_monthly_history SET {sets}, updated_at=? WHERE id=?",
                      list(fields.values()) + [_now(), hid])
            _audit_diff(c, "history", hid, before, fields, list(fields), actor=actor)
        _recalc_history(c, hid)
        _refresh_summary(c, before["account_id"])
        row = c.execute("SELECT * FROM payment_monthly_history WHERE id=?", (hid,)).fetchone()
    return dict(row)


def history_archive(hid: int, on: bool = True, actor: str = "") -> None:
    with _lock, _conn() as c:
        row = c.execute("SELECT account_id FROM payment_monthly_history WHERE id=?", (hid,)).fetchone()
        if not row:
            raise ValueError("history record not found")
        c.execute("UPDATE payment_monthly_history SET is_archived=?, updated_at=? WHERE id=?",
                  (1 if on else 0, _now(), hid))
        _audit(c, "history", hid, "archive" if on else "restore", actor=actor)
        _refresh_summary(c, row["account_id"])


def payment_add(aid: int, data: dict, actor: str = "", source: str = "manual") -> dict:
    amount = _num(data.get("amount"))
    if amount is None or amount <= 0:
        raise ValueError("payment amount must be a positive number")
    pdate = str(data.get("payment_date") or "")[:10]
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", pdate):
        raise ValueError("payment_date must be YYYY-MM-DD")
    status = data.get("payment_status") or "Posted"
    if status not in PAY_TXN_STATUSES:
        raise ValueError(f"payment_status must be one of {PAY_TXN_STATUSES}")
    month = (data.get("statement_month") or "").strip() or None
    if month and not re.match(r"^\d{4}-\d{2}$", month):
        raise ValueError("statement_month must be YYYY-MM")
    conf = re.sub(r"\S(?=\S{4})", "•", str(data.get("confirmation") or ""))[:60]  # keep last 4
    with _lock, _conn() as c:
        if not c.execute("SELECT 1 FROM payment_accounts WHERE id=?", (aid,)).fetchone():
            raise ValueError("account not found")
        hid = None
        if month:
            h = c.execute("SELECT id FROM payment_monthly_history WHERE account_id=? "
                          "AND statement_month=? AND is_archived=0 ORDER BY version DESC LIMIT 1",
                          (aid, month)).fetchone()
            hid = h["id"] if h else None
        cur = c.execute(
            "INSERT INTO payment_transactions (account_id, history_id, payment_date, amount, "
            "payment_method, payment_status, confirmation, notes, statement_month, source_type, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (aid, hid, pdate, amount, (data.get("payment_method") or "")[:60], status, conf,
             (data.get("notes") or "")[:500], month, source, _now(), _now()))
        pid = cur.lastrowid
        _audit(c, "payment", pid, "create", field="amount", new=amount, source=source, actor=actor)
        if hid:
            _recalc_history(c, hid)
        _refresh_summary(c, aid)
        row = c.execute("SELECT * FROM payment_transactions WHERE id=?", (pid,)).fetchone()
    return dict(row)


def payment_update(pid: int, data: dict, actor: str = "") -> dict:
    allowed = {"payment_date", "amount", "payment_method", "payment_status", "confirmation", "notes"}
    with _lock, _conn() as c:
        before = c.execute("SELECT * FROM payment_transactions WHERE id=? AND deleted_at IS NULL",
                           (pid,)).fetchone()
        if not before:
            raise ValueError("payment not found")
        before = dict(before)
        fields = {}
        for f in allowed & set(data):
            v = data[f]
            if f == "amount":
                v = _num(v)
                if v is None or v <= 0:
                    raise ValueError("amount must be positive")
            elif f == "payment_status" and v not in PAY_TXN_STATUSES:
                raise ValueError(f"payment_status must be one of {PAY_TXN_STATUSES}")
            elif f == "payment_date" and not re.match(r"^\d{4}-\d{2}-\d{2}$", str(v or "")):
                raise ValueError("payment_date must be YYYY-MM-DD")
            elif isinstance(v, str):
                v = v.strip()[:500]
            fields[f] = v
        if fields:
            sets = ", ".join(f"{f}=?" for f in fields)
            c.execute(f"UPDATE payment_transactions SET {sets}, updated_at=? WHERE id=?",
                      list(fields.values()) + [_now(), pid])
            _audit_diff(c, "payment", pid, before, fields, list(fields), actor=actor)
        if before["history_id"]:
            _recalc_history(c, before["history_id"])
        _refresh_summary(c, before["account_id"])
        row = c.execute("SELECT * FROM payment_transactions WHERE id=?", (pid,)).fetchone()
    return dict(row)


def payment_delete(pid: int, actor: str = "") -> None:
    with _lock, _conn() as c:
        row = c.execute("SELECT * FROM payment_transactions WHERE id=?", (pid,)).fetchone()
        if not row:
            raise ValueError("payment not found")
        c.execute("UPDATE payment_transactions SET deleted_at=?, updated_at=? WHERE id=?",
                  (_now(), _now(), pid))
        _audit(c, "payment", pid, "delete", actor=actor)
        if row["history_id"]:
            _recalc_history(c, row["history_id"])
        _refresh_summary(c, row["account_id"])


def apply_import_to_account(sid: int, payload: dict, actor: str = "") -> dict:
    """'Apply to Account' from the review panel: map the import to an account (existing or
    new-from-app), write the monthly record (conflict-aware), link the import, refresh summary."""
    init()
    fields = _hist_clean(payload.get("fields") or {})
    month = (payload.get("month") or "").strip()
    if not re.match(r"^\d{4}-\d{2}$", month):
        raise ValueError("month must be YYYY-MM")
    needs_review = bool(payload.get("needs_review"))
    if needs_review:
        fields["payment_status"] = "Needs Review"
    with _lock, _conn() as c:
        shot = c.execute("SELECT * FROM financial_screenshots WHERE id=?", (sid,)).fetchone()
        if not shot:
            raise ValueError("import not found")
        aid = payload.get("account_id")
        if not aid:                          # create the account from the registered app + extraction
            na = payload.get("new_account") or {}
            app = None
            if shot["app_id"]:
                app = c.execute("SELECT * FROM payment_apps WHERE id=?", (shot["app_id"],)).fetchone()
                if app and app["is_archived"]:
                    raise ValueError("this app is archived — restore it before importing")
            acct = _acct_clean(na)
            acct.setdefault("app_id", shot["app_id"])
            acct.setdefault("institution", (app["institution"] if app else "") or na.get("institution") or "")
            acct.setdefault("account_name", na.get("account_name") or (app["name"] if app else shot["app_name"]))
            cols = list(acct) + ["created_at", "updated_at"]
            cur = c.execute(f"INSERT INTO payment_accounts ({','.join(cols)}) "
                            f"VALUES ({','.join('?' * len(cols))})",
                            list(acct.values()) + [_now(), _now()])
            aid = cur.lastrowid
            _audit(c, "account", aid, "create", source="import", actor=actor)
        else:
            row = c.execute("SELECT is_archived, deleted_at FROM payment_accounts WHERE id=?", (aid,)).fetchone()
            if not row:
                raise ValueError("account not found")
            if row["is_archived"] or row["deleted_at"]:
                raise ValueError("account is archived/trashed — restore it before importing")
        hid, conflict = _history_write(c, aid, month, fields, source_type="import",
                                       import_id=sid, resolution=payload.get("resolution"), actor=actor)
        if conflict:
            conflict["account_id"] = aid
            return conflict
        # Account-identity extras that live on the summary row, not the monthly record.
        pf = dict(payload.get("fields") or {})
        if pf.get("masked_account_number") and not pf.get("masked_account"):
            pf["masked_account"] = pf["masked_account_number"]   # extraction-schema key → column name
        extra = _acct_clean({k: pf.get(k) for k in
                             ("available_credit", "credit_limit", "scheduled_payment_amount",
                              "scheduled_payment_date", "autopay_enabled", "masked_account",
                              "account_type", "institution") if pf.get(k) is not None})
        if extra:
            sets = ", ".join(f"{f}=?" for f in extra)
            c.execute(f"UPDATE payment_accounts SET {sets} WHERE id=?", list(extra.values()) + [aid])
        c.execute("UPDATE financial_screenshots SET applied=1, status='applied', month=?, "
                  "account_id=?, history_id=? WHERE id=?", (month, aid, hid, sid))
        _audit(c, "import", sid, "apply", field="account", new=aid, source="import", actor=actor)
        _refresh_summary(c, aid)
    return {"ok": True, "account_id": aid, "history_id": hid}


def expense_line_update(line_id: int, category: str | None = None, delete: bool = False,
                        actor: str = "") -> dict:
    """Expenses-tab links: recategorize or unlink a screenshot-sourced expense line."""
    with _lock, _conn() as c:
        row = c.execute("SELECT * FROM financial_monthly_expenses WHERE id=? AND source='screenshot'",
                        (line_id,)).fetchone()
        if not row:
            raise ValueError("expense line not found (only screenshot-imported lines can be edited here)")
        if delete:
            c.execute("DELETE FROM financial_monthly_expenses WHERE id=?", (line_id,))
            _audit(c, "expense", line_id, "delete", actor=actor)
        elif category:
            c.execute("UPDATE financial_monthly_expenses SET category=? WHERE id=?",
                      (category.strip()[:60], line_id))
            _audit(c, "expense", line_id, "update", "category", row["category"], category, actor=actor)
    return {"ok": True}


def payments_copilot_context(account_ids: list[int] | None = None, include_archived: bool = False) -> str:
    """Structured, credential-free digest of the payment portfolio (or selected accounts)
    for Artik Copilot. Only masked account numbers ever exist in the DB."""
    init()
    with _conn() as c:
        q = ("SELECT a.*, p.name AS app_name FROM payment_accounts a "
             "LEFT JOIN payment_apps p ON p.id=a.app_id WHERE a.deleted_at IS NULL")
        args: list = []
        if account_ids:
            q += f" AND a.id IN ({','.join('?' * len(account_ids))})"
            args += account_ids
        elif not include_archived:
            q += " AND a.is_archived=0"
        accts = [dict(r) for r in c.execute(q, args).fetchall()]
        out = ["PAYMENT ACCOUNTS PORTFOLIO (no credentials; account numbers masked to last-4):"]
        for a in accts:
            out.append(
                f"- {a.get('app_name') or a.get('account_name')} | {a.get('institution') or '?'} "
                f"{a.get('account_type') or ''} ••••{a.get('masked_account') or '????'} | "
                f"balance ${a.get('current_balance') or 0:,.2f}, statement ${a.get('statement_balance') or 0:,.2f}, "
                f"due ${a.get('total_payment_due') or 0:,.2f} (min ${a.get('minimum_payment_due') or 0:,.2f}) "
                f"by {a.get('due_date') or '?'}, remaining ${a.get('remaining_amount_due') or 0:,.2f}, "
                f"last paid ${a.get('last_payment_amount') or 0:,.2f} on {a.get('last_payment_date') or '?'}, "
                f"interest ${a.get('interest_charged') or 0:,.2f}, status {a.get('payment_status') or '?'}"
                + (" [ARCHIVED]" if a.get("is_archived") else ""))
            hist = c.execute("SELECT * FROM payment_monthly_history WHERE account_id=? "
                             "ORDER BY statement_month DESC, version DESC LIMIT 6", (a["id"],)).fetchall()
            for h in hist:
                out.append(f"    {h['statement_month']}: stmt ${h['statement_balance'] or 0:,.2f}, "
                           f"due ${h['total_payment_due'] or 0:,.2f}, paid ${h['total_payments'] or 0:,.2f}, "
                           f"interest ${h['interest_charged'] or 0:,.2f}, {h['payment_status'] or '?'}")
    return "\n".join(out)[:9000]


def screenshot_apply(sid: int, lines: list[dict], month: str, account_group: str) -> dict:
    """Write reviewed extraction lines into monthly expenses (source='screenshot').
    Re-applying the same app+month replaces its previous lines, so re-imports are idempotent."""
    if not month or not re.match(r"^\d{4}-\d{2}$", month):
        raise ValueError("month must be YYYY-MM")
    account_group = (account_group or "screenshot").strip()[:120]
    rows = []
    for ln in lines or []:
        desc = str(ln.get("description") or "").strip()[:300]
        try:
            amt = float(ln.get("amount"))
        except (TypeError, ValueError):
            continue
        if not desc:
            continue
        cat = (ln.get("category") or "").strip() or classify_expense(desc)
        rows.append((account_group, desc, amt, cat, month))
    if not rows:
        raise ValueError("no valid expense lines to apply")
    with _lock, _conn() as c:
        c.execute("DELETE FROM financial_monthly_expenses "
                  "WHERE source='screenshot' AND month=? AND account_group=?", (month, account_group))
        c.executemany("INSERT INTO financial_monthly_expenses "
                      "(account_group,description,amount,category,month,source) "
                      "VALUES (?,?,?,?,?,'screenshot')", rows)
        c.execute("UPDATE financial_screenshots SET applied=1, month=?, status='applied' WHERE id=?",
                  (month, sid))
    return {"ok": True, "applied": len(rows), "month": month, "account_group": account_group}


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


def copilot_context(focus_page: str | None = None) -> str:
    """Compact digest of the ENTIRE financial statement for Artik Copilot — injected server-side
    on every finance-context message so the whole conversation stays aware of all sections
    (net worth, assets, liabilities, cash flow, tax, card APRs, expenses, insights)."""
    try:
        s = summary()
        nw = net_worth()
        a = latest_breakdown("asset")
        lb = latest_breakdown("liability")
        exp = monthly_expenses()
        taxes = tax_income()
        cards = cc_interest()

        def m(v):
            return f"${v:,.0f}" if isinstance(v, (int, float)) else "—"

        lines = [f"PERSONAL FINANCIAL STATEMENT (imported workbook; as of {s.get('as_of')})."]
        if focus_page:
            lines.append(f"The user is currently viewing the '{focus_page}' section.")
        lines.append(
            f"SNAPSHOT: net worth {m(s.get('net_worth'))}; assets {m(s.get('total_assets'))} "
            f"(liquid {m(s.get('liquid_assets'))}); liabilities {m(s.get('total_liabilities'))}; "
            f"debt/assets {s.get('debt_to_asset_pct')}%; monthly income {m(s.get('monthly_income'))}, "
            f"monthly spend {m(s.get('monthly_expenses'))}.")
        st = nw.get("stats") or {}
        lines.append(
            f"NET WORTH: CAGR {st.get('cagr_pct')}%, high {m(st.get('highest'))}, low {m(st.get('lowest'))}, "
            f"avg {m(st.get('average'))}. Timeline: "
            + "; ".join(f"{p['period']} {m(p['net_worth'])}" for p in nw.get("points", [])))
        lines.append("ASSET MIX (" + str(a.get("period")) + "): "
                     + ", ".join(f"{k} {m(v)}" for k, v in (a.get("categories") or {}).items())
                     + ". Accounts: "
                     + ", ".join(f"{r['item']} {m(r['value'])}" for r in (a.get("items") or [])
                                 if (r.get("value") or 0) > 0))
        lines.append("LIABILITIES (" + str(lb.get("period")) + "): "
                     + ", ".join(f"{k} {m(v)}" for k, v in (lb.get("categories") or {}).items())
                     + ". Items: "
                     + ", ".join(f"{r['item']} {m(r['value'])}" for r in (lb.get("items") or [])
                                 if (r.get("value") or 0) > 0))
        lines.append("TAX & INCOME by year: "
                     + "; ".join(f"{t['year']}: income {m(t.get('total_income'))} "
                                 f"(wages {m(t.get('wages'))}, cap-gain {m(t.get('capital_gain'))})"
                                 for t in taxes))
        lines.append("CARD APRs: " + "; ".join(
            f"{c['card']} purchase {c.get('purchase_apr')}" for c in cards))
        lines.append("MONTHLY SPEND by category: "
                     + ", ".join(f"{k} {m(v)}" for k, v in (exp.get("categories") or {}).items())
                     + f". Income {m(exp.get('monthly_income'))} vs spend {m(exp.get('monthly_spend'))}.")
        lines.append("COMPUTED INSIGHTS: " + " ".join(insights()))
        return "\n".join(lines)[:7000]
    except Exception as e:  # noqa: BLE001
        return f"(financial statement context unavailable: {e})"


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
