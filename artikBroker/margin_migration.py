"""Margin gross-up migration — deduct margin debt exactly once.

ROOT CAUSE
----------
Brokerage asset values were captured as *net account value* (gross securities + cash − margin
debt), while the same margin balance was also recorded on the Liability page. Net worth is
``assets − liabilities``, so margin was subtracted twice::

    netWorth = (grossBrokerage − margin) − margin

THE FIX
-------
Store brokerage assets **gross** (before margin), keep margin as a liability, and let net worth
subtract it once::

    grossBrokerageAssets = netBrokerageValue + marginDebt
    netWorth             = totalAssets − totalLiabilities

Only margin is added back. Mortgages, credit cards, loans and every other liability are left
alone — they were never netted against an asset.

SAFETY
------
Every eligible row carries ``asset_value_basis``. The add-back runs only on rows marked
``net``; the row is flipped to ``gross`` afterwards, so a second run is a no-op. Original rows
are copied into ``financial_migration_backup`` before any write, and ``rollback()`` restores
them exactly.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import finance

MIGRATION = "margin_gross_up"
VERSION = 1

BROKERAGE_CATEGORY = "Brokerage"
MARGIN_CATEGORY = "Margin"

# Row that absorbs margin we cannot attribute to a specific account, so the brokerage subtotal
# is exactly right without inventing account-level precision.
UNALLOCATED_ITEM = "Margin gross-up (unallocated)"

# ── Explicit account mapping ────────────────────────────────────────────────────────────────
# Margin liability item  ->  brokerage asset item, by era. Names changed with the
# Ameritrade -> Schwab migration; a renamed account is the SAME account, never an extra one.
#   confidence "exact"    — the margin item names an asset item present in that period
#   confidence "mapped"   — documented rename/migration (TD Ameritrade -> Schwab 1,
#                           Charles Schwab -> Schwab 2, later relabelled "Charles Main")
# Anything not resolved here falls back to the period-level subtotal rule.
ACCOUNT_MAP = [
    # (margin item, asset item, confidence, note)
    ("eTrade", "eTrade", "exact", "same account, unchanged name"),
    ("Ameritrade", "Ameritrade", "exact", "pre-migration Ameritrade account"),
    ("Ameritrade", "Schwab 1", "mapped",
     "TD Ameritrade migrated to Schwab; continues as Schwab 1 (relabelled 'Charles Main' from 2026 Q2)"),
    ("Charles Main", "Schwab 1", "mapped", "2026+ label for the migrated Ameritrade/Schwab 1 account"),
    ("Charles", "Schwab", "exact", "Charles Schwab account, pre-migration name"),
    ("Charles", "Schwab 2", "mapped", "Charles Schwab account, post-migration name"),
]
# Margin items that are known aggregates/placeholders rather than accounts.
AGGREGATE_MARGIN_ITEMS = {"Debt (Stock Margin)"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _plabel(y, q) -> str:
    return f"Q{q} {y}" if q else str(y)


def _pkey(y, q) -> float:
    return y + ((q or 4) / 10.0)


# ── schema ──────────────────────────────────────────────────────────────────────────────────
def ensure_schema() -> None:
    """Idempotent: add the value-basis columns and the backup/log tables if absent."""
    finance.init()
    with finance._lock, finance._conn() as c:
        cols = {r["name"] for r in c.execute("PRAGMA table_info(financial_records)")}
        if "asset_value_basis" not in cols:
            c.execute("ALTER TABLE financial_records ADD COLUMN asset_value_basis TEXT")
        if "margin_migration_version" not in cols:
            c.execute("ALTER TABLE financial_records ADD COLUMN margin_migration_version INTEGER DEFAULT 0")
        c.execute("""CREATE TABLE IF NOT EXISTS financial_migration_backup (
            id INTEGER PRIMARY KEY AUTOINCREMENT, migration TEXT, version INTEGER, ts TEXT,
            record_id INTEGER, dataset TEXT, item TEXT, category TEXT, liquid INTEGER,
            year INTEGER, quarter INTEGER, value REAL, is_total INTEGER, source_sheet TEXT,
            asset_value_basis TEXT, created INTEGER DEFAULT 0)""")
        c.execute("""CREATE TABLE IF NOT EXISTS financial_migration_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, migration TEXT, version INTEGER, ts TEXT,
            actor TEXT, action TEXT, detail TEXT)""")
        # Existing brokerage rows predate the fix, so they hold NET values by definition.
        c.execute("UPDATE financial_records SET asset_value_basis='net' "
                  "WHERE dataset='asset' AND category=? AND is_total=0 AND asset_value_basis IS NULL "
                  "AND item<>?", (BROKERAGE_CATEGORY, UNALLOCATED_ITEM))


# ── reading ─────────────────────────────────────────────────────────────────────────────────
def _load(c):
    """{(year, quarter): {'assets': {item: row}, 'margin': {item: value}}} plus period totals."""
    per: dict = {}
    for r in c.execute("SELECT id, item, category, year, quarter, value, asset_value_basis "
                       "FROM financial_records WHERE dataset='asset' AND category=? AND is_total=0",
                       (BROKERAGE_CATEGORY,)):
        per.setdefault((r["year"], r["quarter"]), {}).setdefault("assets", {})[r["item"]] = dict(r)
    for r in c.execute("SELECT item, year, quarter, value FROM financial_records "
                       "WHERE dataset='liability' AND category=? AND is_total=0", (MARGIN_CATEGORY,)):
        per.setdefault((r["year"], r["quarter"]), {}).setdefault("margin", {})[r["item"]] = r["value"] or 0
    return per


def _totals(c, dataset: str) -> dict:
    return {(r["year"], r["quarter"]): (r["t"] or 0) for r in c.execute(
        "SELECT year, quarter, SUM(value) AS t FROM financial_records "
        "WHERE dataset=? AND is_total=0 GROUP BY year, quarter", (dataset,))}


def resolve_account(margin_item: str, assets: dict) -> tuple:
    """(asset_item | None, method, note) for one margin item within one period."""
    if margin_item in AGGREGATE_MARGIN_ITEMS:
        return None, "aggregate", "known aggregate row, not an account"
    for m_item, a_item, conf, note in ACCOUNT_MAP:
        if m_item == margin_item and a_item in assets:
            return a_item, conf, note
    if margin_item in assets:                      # same-name account not in the table
        return margin_item, "exact", "name matches a brokerage account in this period"
    return None, "unresolved", "no brokerage account matched; period-subtotal fallback used"


# ── dry run ─────────────────────────────────────────────────────────────────────────────────
def dry_run() -> dict:
    """Reconciliation report. Reads only — never writes."""
    ensure_schema()
    with finance._conn() as c:
        per = _load(c)
        at, lt = _totals(c, "asset"), _totals(c, "liability")
        dup = _duplicate_accounts(c)
    rows: list = []
    warnings: list = list(dup)
    tot_addback = 0.0
    for p in sorted(per, key=lambda k: _pkey(*k)):
        assets = per[p].get("assets", {})
        margins = {k: v for k, v in per[p].get("margin", {}).items() if v}
        if not margins:
            continue
        eligible = {k: v for k, v in assets.items()
                    if (v.get("asset_value_basis") or "net") == "net"}
        if not eligible and any((v.get("asset_value_basis") == "gross") for v in assets.values()):
            continue                                            # already migrated
        alloc: dict = {}
        methods: dict = {}
        unresolved = 0.0
        for m_item, m_val in sorted(margins.items()):
            tgt, method, _note = resolve_account(m_item, eligible)
            if tgt:
                alloc[tgt] = alloc.get(tgt, 0) + m_val
                methods.setdefault(tgt, []).append(f"{m_item} → {tgt} ({method})")
            else:
                unresolved += m_val
                methods.setdefault(UNALLOCATED_ITEM, []).append(
                    f"{m_item} → period subtotal ({method})")
                if method == "unresolved":
                    warnings.append(
                        f"{_plabel(*p)}: margin item '{m_item}' ({finance._m(m_val)}) could not be "
                        f"mapped to a brokerage account — added at period level instead.")
        period_margin = sum(margins.values())
        tot_addback += period_margin
        oa, ol = at.get(p, 0), lt.get(p, 0)
        shared = {"original_total_assets": round(oa, 2),
                  "corrected_total_assets": round(oa + period_margin, 2),
                  "total_liabilities": round(ol, 2),
                  "original_net_worth": round(oa - ol, 2),
                  "corrected_net_worth": round(oa + period_margin - ol, 2)}
        targets = sorted(alloc) + ([UNALLOCATED_ITEM] if unresolved else [])
        for item in targets:
            add = unresolved if item == UNALLOCATED_ITEM else alloc[item]
            orig = (eligible.get(item, {}) or {}).get("value", 0) or 0
            rows.append({"period": _plabel(*p), "year": p[0], "quarter": p[1], "account": item,
                         "original_net": round(orig, 2), "margin_added_back": round(add, 2),
                         "corrected_gross": round(orig + add, 2),
                         "mapping_method": "; ".join(methods.get(item, [])) or "period fallback",
                         "new_row": item == UNALLOCATED_ITEM and item not in assets,
                         **shared})
    return {"migration": MIGRATION, "version": VERSION, "rows": rows,
            "periods": len({r["period"] for r in rows}),
            "total_margin_added_back": round(tot_addback, 2),
            "warnings": warnings, "applied": is_applied(), "dry_run": True}


def _duplicate_accounts(c) -> list:
    """A renamed account must not be counted twice in the same period."""
    out = []
    pairs = [("Ameritrade", "Schwab 1"), ("Schwab", "Schwab 2")]
    per: dict = {}
    for r in c.execute("SELECT item, year, quarter, value FROM financial_records "
                       "WHERE dataset='asset' AND category=? AND is_total=0", (BROKERAGE_CATEGORY,)):
        per.setdefault((r["year"], r["quarter"]), {})[r["item"]] = r["value"] or 0
    for p, items in sorted(per.items(), key=lambda kv: _pkey(*kv[0])):
        for old, new in pairs:
            a, b = items.get(old), items.get(new)
            if a and b and abs(a - b) < 0.01:
                out.append(f"{_plabel(*p)}: '{old}' and '{new}' both hold {finance._m(a)} — the same "
                           f"account counted twice ({finance._m(a)} of double-counted assets). "
                           f"NOT changed by this migration; fix separately.")
    return out


# ── state ───────────────────────────────────────────────────────────────────────────────────
def is_applied() -> bool:
    """Current state, not history: the newest apply/rollback entry wins, so a rolled-back
    migration correctly reports as not applied and can be applied again."""
    ensure_schema()
    with finance._conn() as c:
        r = c.execute("SELECT action FROM financial_migration_log WHERE migration=? AND version=? "
                      "AND action IN ('apply','rollback') ORDER BY id DESC LIMIT 1",
                      (MIGRATION, VERSION)).fetchone()
        return bool(r) and r["action"] == "apply"


def status() -> dict:
    ensure_schema()
    with finance._conn() as c:
        basis = {r["b"] or "unset": r["n"] for r in c.execute(
            "SELECT asset_value_basis b, COUNT(*) n FROM financial_records "
            "WHERE dataset='asset' AND category=? AND is_total=0 GROUP BY 1", (BROKERAGE_CATEGORY,))}
        log = [dict(r) for r in c.execute(
            "SELECT ts, actor, action, detail FROM financial_migration_log "
            "WHERE migration=? ORDER BY id DESC LIMIT 10", (MIGRATION,))]
        bk = c.execute("SELECT COUNT(*) n FROM financial_migration_backup WHERE migration=?",
                       (MIGRATION,)).fetchone()["n"]
    return {"migration": MIGRATION, "version": VERSION, "applied": is_applied(),
            "rows_by_basis": basis, "backup_rows": bk, "log": log}


# ── apply / rollback ────────────────────────────────────────────────────────────────────────
def apply(actor: str = "", confirm: bool = False) -> dict:
    """Add margin back to net brokerage rows. Idempotent: 'gross' rows are never touched."""
    if not confirm:
        raise ValueError("confirm=true is required to apply the historical migration")
    ensure_schema()
    report = dry_run()
    ts = _now()
    applied = created = 0
    with finance._lock, finance._conn() as c:
        per = _load(c)
        for p in sorted(per, key=lambda k: _pkey(*k)):
            assets = per[p].get("assets", {})
            margins = per[p].get("margin", {})
            if not margins:
                continue
            eligible = {k: v for k, v in assets.items()
                        if (v.get("asset_value_basis") or "net") == "net"}
            # Already migrated: brokerage rows exist for this period and every one is 'gross'.
            # Without this guard a re-run would find no eligible target, treat all margin as
            # unresolved, and add it a second time through the unallocated row.
            if not eligible and any(v.get("asset_value_basis") == "gross" for v in assets.values()):
                continue
            alloc, unresolved = {}, 0.0
            for m_item, m_val in margins.items():
                if not m_val:
                    continue
                tgt, method, _n = resolve_account(m_item, eligible)
                if tgt:
                    alloc[tgt] = alloc.get(tgt, 0) + m_val
                else:
                    unresolved += m_val
            for item, add in alloc.items():
                row = eligible.get(item)
                if not row or not add:
                    continue
                _backup(c, ts, row["id"], created=0)
                c.execute("UPDATE financial_records SET value=?, asset_value_basis='gross', "
                          "margin_migration_version=? WHERE id=?",
                          (round((row["value"] or 0) + add, 2), VERSION, row["id"]))
                applied += 1
            if unresolved:
                ex = c.execute("SELECT id, value, asset_value_basis FROM financial_records "
                               "WHERE dataset='asset' AND item=? AND year=? AND quarter IS ?",
                               (UNALLOCATED_ITEM, p[0], p[1])).fetchone()
                if ex:
                    if (ex["asset_value_basis"] or "net") == "net":
                        _backup(c, ts, ex["id"], created=0)
                        c.execute("UPDATE financial_records SET value=?, asset_value_basis='gross', "
                                  "margin_migration_version=? WHERE id=?",
                                  (round((ex["value"] or 0) + unresolved, 2), VERSION, ex["id"]))
                        applied += 1
                else:
                    cur = c.execute(
                        "INSERT INTO financial_records (dataset,item,category,liquid,year,quarter,"
                        "value,is_total,source_sheet,asset_value_basis,margin_migration_version) "
                        "VALUES ('asset',?,?,1,?,?,?,0,'margin-gross-up','gross',?)",
                        (UNALLOCATED_ITEM, BROKERAGE_CATEGORY, p[0], p[1],
                         round(unresolved, 2), VERSION))
                    _backup(c, ts, cur.lastrowid, created=1)
                    created += 1
            # every remaining net brokerage row in this period is now gross by definition
            for item, row in eligible.items():
                if item not in alloc:
                    c.execute("UPDATE financial_records SET asset_value_basis='gross', "
                              "margin_migration_version=? WHERE id=?", (VERSION, row["id"]))
        # brokerage rows in periods with no margin at all are already gross
        c.execute("UPDATE financial_records SET asset_value_basis='gross', margin_migration_version=? "
                  "WHERE dataset='asset' AND category=? AND is_total=0 "
                  "AND COALESCE(asset_value_basis,'net')='net'", (VERSION, BROKERAGE_CATEGORY))
        c.execute("INSERT INTO financial_migration_log (migration,version,ts,actor,action,detail) "
                  "VALUES (?,?,?,?,'apply',?)",
                  (MIGRATION, VERSION, ts, actor,
                   json.dumps({"rows_updated": applied, "rows_created": created,
                               "margin_added_back": report["total_margin_added_back"]})))
    return {"ok": True, "rows_updated": applied, "rows_created": created,
            "margin_added_back": report["total_margin_added_back"],
            "warnings": report["warnings"]}


def _backup(c, ts: str, record_id: int, created: int) -> None:
    c.execute("""INSERT INTO financial_migration_backup
        (migration,version,ts,record_id,dataset,item,category,liquid,year,quarter,value,is_total,
         source_sheet,asset_value_basis,created)
        SELECT ?,?,?,id,dataset,item,category,liquid,year,quarter,value,is_total,source_sheet,
               asset_value_basis,? FROM financial_records WHERE id=?""",
              (MIGRATION, VERSION, ts, created, record_id))


def rollback(actor: str = "") -> dict:
    """Restore the pre-migration values from the backup and clear the gross marking."""
    ensure_schema()
    restored = removed = 0
    with finance._lock, finance._conn() as c:
        bk = [dict(r) for r in c.execute(
            "SELECT * FROM financial_migration_backup WHERE migration=? AND version=? ORDER BY id",
            (MIGRATION, VERSION))]
        if not bk:
            return {"ok": False, "error": "no backup rows for this migration — nothing to roll back"}
        for b in bk:
            if b["created"]:
                c.execute("DELETE FROM financial_records WHERE id=?", (b["record_id"],))
                removed += 1
            else:
                c.execute("UPDATE financial_records SET value=?, asset_value_basis=?, "
                          "margin_migration_version=0 WHERE id=?",
                          (b["value"], b["asset_value_basis"], b["record_id"]))
                restored += 1
        # rows only re-marked (not value-changed) go back to 'net'
        c.execute("UPDATE financial_records SET asset_value_basis='net', margin_migration_version=0 "
                  "WHERE dataset='asset' AND category=? AND is_total=0 AND asset_value_basis='gross'",
                  (BROKERAGE_CATEGORY,))
        c.execute("DELETE FROM financial_migration_backup WHERE migration=? AND version=?",
                  (MIGRATION, VERSION))
        c.execute("INSERT INTO financial_migration_log (migration,version,ts,actor,action,detail) "
                  "VALUES (?,?,?,?,'rollback',?)",
                  (MIGRATION, VERSION, _now(), actor,
                   json.dumps({"restored": restored, "removed": removed})))
    return {"ok": True, "restored": restored, "removed": removed}
