"""ArtikFinance Alerts — validation, scheduling, evaluation, and Slack formatting.

This is the safe core. It NEVER executes user text: the chatbot produces a structured rule
which is validated here against strict allow-lists (sources / metrics / fields / operators /
frequencies / destinations). Evaluation reads the EXISTING finance functions only. State-change
+ cooldown logic decides whether a Slack notification should fire.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo, available_timezones
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore
    available_timezones = lambda: set()  # noqa: E731

import finance

DEFAULT_TZ = "America/Los_Angeles"

# ── allow-lists ───────────────────────────────────────────────────────────────
OPERATORS = {">", ">=", "<", "<=", "=", "!=", "within_days", "overdue_by_days",
             "percentage_increase_greater_than", "percentage_decrease_greater_than",
             "absolute_change_greater_than", "not_updated_for_days"}
_NUMERIC_OPS = {">", ">=", "<", "<=", "=", "!="}
_CHANGE_OPS = {"percentage_increase_greater_than", "percentage_decrease_greater_than",
               "absolute_change_greater_than"}
_ROW_OPS = {"within_days", "overdue_by_days", "not_updated_for_days"}
FREQUENCIES = {"hourly", "daily", "weekly", "monthly", "quarterly"}
LOGICAL = {"AND", "OR"}
TRIGGER_MODES = {"state_change", "notify_once", "every_run", "once_per_day"}
CHANNELS = {"slack"}
DESTINATION_TYPES = {"channel", "user", "default"}

# source_type → {metric fields that are SCALAR, row-wise fields, filter keys}
SOURCES: dict[str, dict] = {
    "payment_accounts": {
        "scalars": {"total_current_balance", "statement_balance", "minimum_due", "total_due",
                    "remaining_due", "interest", "credit_card_interest", "paid_this_month",
                    "overdue_count", "due_soon_count"},
        "rows": {"due_date", "remaining_amount_due", "current_balance", "total_payment_due",
                 "updated_at"},
        "filters": {"account_type", "status", "institution", "account"},
    },
    "assets": {"scalars": {"total_assets", "category_total"}, "rows": set(),
               "filters": {"category", "item"}},
    "liabilities": {"scalars": {"total_debt", "category_total"}, "rows": set(),
                    "filters": {"category", "item"}},
    "net_worth": {"scalars": {"net_worth", "assets", "liabilities"}, "rows": set(), "filters": set()},
    "monthly_expenses": {"scalars": {"monthly_spend", "monthly_income", "category_total"},
                         "rows": set(), "filters": {"category"}},
    "cashflow": {"scalars": {"cashflow_metric"}, "rows": set(), "filters": {"metric_name"}},
    "broker_account": {"scalars": {"total_value", "total_gain"}, "rows": set(),
                       "filters": {"broker", "account_ending"}},
}


class AlertError(ValueError):
    pass


# Fields that belong to exactly one source — used to recover a missing/blank source that
# the LLM occasionally omits (the conditions still name the fields correctly).
_FIELD_TO_SOURCE: dict[str, str] = {}
for _src, _spec in {
    "payment_accounts": {"total_current_balance", "statement_balance", "minimum_due", "total_due",
                         "remaining_due", "interest", "credit_card_interest", "paid_this_month",
                         "overdue_count", "due_soon_count", "due_date", "remaining_amount_due",
                         "current_balance", "total_payment_due", "updated_at"},
    "assets": {"total_assets"}, "liabilities": {"total_debt"},
    "net_worth": {"net_worth"}, "monthly_expenses": {"monthly_spend", "monthly_income"},
    "cashflow": {"cashflow_metric"}, "broker_account": {"total_value", "total_gain"},
}.items():
    for _f in _spec:
        _FIELD_TO_SOURCE[_f] = _src


def infer_source(conditions) -> str | None:
    for c in conditions or []:
        s = _FIELD_TO_SOURCE.get(str((c or {}).get("field") or "").strip())
        if s:
            return s
    return None


def _num(v):
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


def sanitize_text(s: str, limit: int = 200) -> str:
    """Strip control chars / HTML-ish angle brackets from chatbot-generated names."""
    s = re.sub(r"[<>\x00-\x1f]", "", str(s or "")).strip()
    return s[:limit]


def valid_timezone(tz: str) -> bool:
    if not tz:
        return False
    try:
        if ZoneInfo is None:
            return tz == DEFAULT_TZ
        ZoneInfo(tz)
        return True
    except Exception:  # noqa: BLE001
        return False


# ── validation ────────────────────────────────────────────────────────────────
def validate_alert(alert: dict) -> dict:
    """Return a normalized, fully-validated alert dict, or raise AlertError."""
    if not isinstance(alert, dict):
        raise AlertError("alert must be an object")
    name = sanitize_text(alert.get("name") or "")
    if not name:
        raise AlertError("alert name is required")
    source = str(alert.get("source") or alert.get("source_type") or "").strip()
    if not source:                                   # LLM sometimes omits it — recover from fields
        source = infer_source(alert.get("conditions")) or ""
    if source not in SOURCES:
        raise AlertError(f"unsupported source '{source}' (allowed: {sorted(SOURCES)})")
    spec = SOURCES[source]

    filters = alert.get("filters") or {}
    if not isinstance(filters, dict):
        raise AlertError("filters must be an object")
    for k in filters:
        if k not in spec["filters"]:
            raise AlertError(f"unsupported filter '{k}' for source '{source}'")

    conditions = alert.get("conditions") or []
    if not isinstance(conditions, list) or not conditions:
        raise AlertError("at least one condition is required")
    allowed_fields = spec["scalars"] | spec["rows"]
    norm_conds = []
    for c in conditions:
        if not isinstance(c, dict):
            raise AlertError("each condition must be an object")
        field = str(c.get("field") or "").strip()
        op = str(c.get("operator") or "").strip()
        if op not in OPERATORS:
            raise AlertError(f"unsupported operator '{op}'")
        if field not in allowed_fields:
            raise AlertError(f"unsupported field '{field}' for source '{source}'")
        if op in _ROW_OPS and field not in spec["rows"]:
            raise AlertError(f"operator '{op}' needs a row-wise field, not '{field}'")
        val = _num(c.get("value"))
        if val is None:
            raise AlertError(f"condition on '{field}' needs a numeric value")
        norm_conds.append({"field": field, "operator": op, "value": val})

    logical = str(alert.get("logical_operator") or "AND").upper()
    if logical not in LOGICAL:
        raise AlertError("logical_operator must be AND or OR")

    sch = alert.get("schedule") or {}
    freq = str(sch.get("frequency") or "daily").lower()
    if freq not in FREQUENCIES:
        raise AlertError(f"unsupported frequency '{freq}'")
    time_str = str(sch.get("time") or "08:00").strip()
    if not re.match(r"^([01]?\d|2[0-3]):[0-5]\d$", time_str):
        raise AlertError("schedule time must be HH:MM (24h)")
    tz = str(sch.get("timezone") or DEFAULT_TZ).strip()
    if not valid_timezone(tz):
        raise AlertError(f"invalid timezone '{tz}'")

    notif = alert.get("notification") or {}
    channel = str(notif.get("channel") or "slack").lower()
    if channel not in CHANNELS:
        raise AlertError("only the 'slack' channel is supported")
    dtype = str(notif.get("destination_type") or "default").lower()
    if dtype not in DESTINATION_TYPES:
        raise AlertError("destination_type must be channel, user, or default")
    dest = sanitize_text(notif.get("destination") or "", 80)
    if dtype == "channel" and dest and not dest.startswith("#"):
        dest = "#" + dest.lstrip("#")
    if dtype == "user" and dest and not dest.startswith("@"):
        dest = "@" + dest.lstrip("@")

    trigger_mode = str(alert.get("trigger_mode") or "state_change").lower()
    if trigger_mode not in TRIGGER_MODES:
        raise AlertError(f"unsupported trigger_mode '{trigger_mode}'")
    cooldown = int(_num(alert.get("cooldown_minutes")) or 1440)

    metric = str(alert.get("metric") or (norm_conds[0]["field"] if norm_conds else "") or "")
    return {
        "name": name, "description": sanitize_text(alert.get("description") or "", 500),
        "source_type": source, "metric": metric, "filters": filters, "conditions": norm_conds,
        "logical_operator": logical,
        "schedule": {"frequency": freq, "time": time_str, "timezone": tz},
        "notification": {"channel": channel, "destination_type": dtype, "destination": dest},
        "trigger_mode": trigger_mode, "cooldown_minutes": max(0, cooldown),
        "is_enabled": bool(alert.get("is_enabled", True)),
    }


# ── scheduling ────────────────────────────────────────────────────────────────
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def compute_next_run(schedule: dict, after: datetime | None = None) -> str:
    """Next fire time as UTC ISO 'Z', from {frequency,time,timezone}."""
    after = after or _utcnow()
    freq = schedule.get("frequency", "daily")
    tzname = schedule.get("timezone", DEFAULT_TZ)
    tz = ZoneInfo(tzname) if (ZoneInfo and valid_timezone(tzname)) else timezone.utc
    hh, mm = (schedule.get("time") or "08:00").split(":")
    hh, mm = int(hh), int(mm)
    local = after.astimezone(tz)

    if freq == "hourly":
        nxt = (local.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
        return nxt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    cand = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if freq == "daily":
        if cand <= local:
            cand += timedelta(days=1)
    elif freq == "weekly":
        if cand <= local:
            cand += timedelta(days=7)
    elif freq == "monthly":
        if cand <= local:
            cand = _add_months(cand, 1)
    elif freq == "quarterly":
        if cand <= local:
            cand = _add_months(cand, 3)
    return cand.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _add_months(dt: datetime, n: int) -> datetime:
    m = dt.month - 1 + n
    y = dt.year + m // 12
    m = m % 12 + 1
    import calendar
    d = min(dt.day, calendar.monthrange(y, m)[1])
    return dt.replace(year=y, month=m, day=d)


# ── data resolution (reads existing finance.* only) ──────────────────────────
def _mask_label(row: dict) -> str:
    name = row.get("app_name") or row.get("account_name") or row.get("institution") or "Account"
    m = row.get("masked_account")
    return f"{name} ••••{m}" if m else str(name)


def _payment_rows(filters: dict) -> list[dict]:
    data = finance.accounts_list("active")
    rows = data.get("accounts") or []
    ftype = [s.lower() for s in (filters.get("account_type") or [])]
    fstat = [s.lower() for s in (filters.get("status") or [])]
    finst = [s.lower() for s in (filters.get("institution") or [])]
    facct = [s.lower() for s in (filters.get("account") or [])]
    out = []
    for r in rows:
        if ftype and (r.get("account_type") or "").lower() not in ftype:
            # allow substring match e.g. "credit card" in "Business Credit Card"
            if not any(t in (r.get("account_type") or "").lower() for t in ftype):
                continue
        if fstat and (r.get("payment_status") or "").lower() not in fstat:
            if not (("active" in fstat) and (r.get("payment_status") not in (None, "", "No Payment Required"))):
                continue
        if finst and (r.get("institution") or "").lower() not in finst:
            continue
        if facct and not any(a in ((r.get("app_name") or "") + (r.get("account_name") or "")).lower() for a in facct):
            continue
        out.append(r)
    return out, data.get("metrics") or {}


def _quarter_prev(timeline: list[dict], key="total") -> tuple[float | None, float | None]:
    """(current, previous) from a period timeline (last two points)."""
    pts = [p for p in (timeline or []) if p.get(key) is not None]
    if len(pts) >= 2:
        return pts[-1][key], pts[-2][key]
    if len(pts) == 1:
        return pts[-1][key], None
    return None, None


def resolve(source: str, filters: dict) -> dict:
    """Return {'scalars': {...}, 'prev': {...}, 'rows': [...], 'affected': [...]}."""
    filters = filters or {}
    if source == "payment_accounts":
        rows, metrics = _payment_rows(filters)
        summ = lambda k: round(sum(_num(r.get(k)) or 0 for r in rows), 2)  # noqa: E731
        scalars = {
            "total_current_balance": summ("current_balance"),
            "statement_balance": summ("statement_balance"),
            "minimum_due": summ("minimum_payment_due"),
            "total_due": summ("total_payment_due"),
            "remaining_due": summ("remaining_amount_due"),
            "interest": summ("interest_charged"),
            "credit_card_interest": summ("interest_charged"),
            "paid_this_month": metrics.get("paid_this_month"),
            "overdue_count": sum(1 for r in rows if r.get("payment_status") == "Overdue"),
            "due_soon_count": sum(1 for r in rows if r.get("payment_status") == "Due Soon"),
        }
        affected = [{"label": _mask_label(r), "amount": _num(r.get("current_balance"))} for r in rows]
        return {"scalars": scalars, "prev": {}, "rows": rows, "affected": affected}

    if source in ("assets", "liabilities"):
        ds = "asset" if source == "assets" else "liability"
        cats = filters.get("category") or []
        items = filters.get("item") or []
        params = {"categories": ",".join(cats), "items": "|".join(items)}
        d = finance.assets_search(params, dataset=ds)
        total = d["summary"].get("total_assets")  # engine reuses key name for both datasets
        cur, prev = _quarter_prev(d.get("timeline") or [], "total")
        scalars = {("total_assets" if ds == "asset" else "total_debt"): total,
                   "category_total": total}
        cat_totals = d["summary"].get("category_totals") or {}
        affected = [{"label": k, "amount": v} for k, v in cat_totals.items()]
        return {"scalars": scalars, "prev": {"__total__": prev, "cur": cur}, "rows": [], "affected": affected}

    if source == "net_worth":
        nw = finance.net_worth()
        pts = nw.get("points") or []
        cur = (nw.get("stats") or {}).get("current")
        prev = pts[-2]["net_worth"] if len(pts) >= 2 else None
        aprev = pts[-2]["assets"] if len(pts) >= 2 else None
        lprev = pts[-2]["liabilities"] if len(pts) >= 2 else None
        last = pts[-1] if pts else {}
        scalars = {"net_worth": cur, "assets": last.get("assets"), "liabilities": last.get("liabilities")}
        return {"scalars": scalars,
                "prev": {"net_worth": prev, "assets": aprev, "liabilities": lprev},
                "rows": [], "affected": [{"label": "Net worth", "amount": cur}]}

    if source == "monthly_expenses":
        e = finance.monthly_expenses()
        cats = [c.lower() for c in (filters.get("category") or [])]
        cat_total = sum(v for k, v in (e.get("categories") or {}).items() if not cats or k.lower() in cats)
        scalars = {"monthly_spend": e.get("monthly_spend"), "monthly_income": e.get("monthly_income"),
                   "category_total": round(cat_total, 2)}
        affected = [{"label": k, "amount": v} for k, v in (e.get("categories") or {}).items()]
        return {"scalars": scalars, "prev": {}, "rows": [], "affected": affected}

    if source == "cashflow":
        cf = finance.cashflow_series()
        want = (filters.get("metric_name") or ["Total"])
        want = want[0] if isinstance(want, list) else want
        val, prev = None, None
        for s in cf.get("series") or []:
            if s["name"].lower() == str(want).lower():
                pts = [p["value"] for p in s["points"] if p["value"] is not None]
                val = pts[-1] if pts else None
                prev = pts[-2] if len(pts) >= 2 else None
        return {"scalars": {"cashflow_metric": val}, "prev": {"cashflow_metric": prev},
                "rows": [], "affected": [{"label": str(want), "amount": val}]}

    if source == "broker_account":
        try:
            import portfolio_store
            broker = (filters.get("broker") or [None])
            broker = (broker[0] if isinstance(broker, list) else broker)
            snaps = portfolio_store.list_snapshots(source=broker)
            if snaps:
                s = snaps[0]
                return {"scalars": {"total_value": s.get("total_value"), "total_gain": s.get("total_gain")},
                        "prev": {}, "rows": [],
                        "affected": [{"label": (s.get("label") or broker or "Broker"),
                                      "amount": s.get("total_value")}]}
        except Exception:  # noqa: BLE001
            pass
        return {"scalars": {"total_value": None, "total_gain": None}, "prev": {}, "rows": [], "affected": []}

    raise AlertError(f"no resolver for source '{source}'")


# ── condition evaluation ──────────────────────────────────────────────────────
def _cmp(op: str, a, b) -> bool:
    if a is None:
        return False
    return {">": a > b, ">=": a >= b, "<": a < b, "<=": a <= b,
            "=": abs(a - b) < 1e-9, "!=": abs(a - b) >= 1e-9}[op]


def _parse_date(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s)[:19].replace("Z", "")).date()
    except ValueError:
        try:
            return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def _eval_condition(cond: dict, ctx: dict) -> tuple[bool, object, list]:
    """Return (met, evaluated_value, affected_rows)."""
    field, op, val = cond["field"], cond["operator"], cond["value"]
    if op in _NUMERIC_OPS:
        cur = ctx["scalars"].get(field)
        return _cmp(op, cur, val), cur, ctx.get("affected", [])
    if op in _CHANGE_OPS:
        cur = ctx["scalars"].get(field)
        prev = (ctx.get("prev") or {}).get(field)
        if prev in (None, 0) and (ctx.get("prev") or {}).get("cur") is not None:
            cur, prev = ctx["prev"].get("cur"), ctx["prev"].get("__total__")
        if cur is None or prev in (None, 0):
            return False, {"current": cur, "previous": prev}, ctx.get("affected", [])
        if op == "percentage_increase_greater_than":
            met = (cur - prev) / abs(prev) * 100 > val
        elif op == "percentage_decrease_greater_than":
            met = (prev - cur) / abs(prev) * 100 > val
        else:  # absolute_change_greater_than
            met = abs(cur - prev) > val
        return met, {"current": cur, "previous": prev}, ctx.get("affected", [])
    # row-wise operators
    today = _utcnow().date()
    matches = []
    for r in ctx.get("rows", []):
        if op == "within_days":
            d = _parse_date(r.get("due_date"))
            rem = _num(r.get("remaining_amount_due"))
            if d and 0 <= (d - today).days <= val and (rem is None or rem > 0):
                matches.append(r)
        elif op == "overdue_by_days":
            d = _parse_date(r.get("due_date"))
            rem = _num(r.get("remaining_amount_due"))
            if d and (today - d).days >= val and (rem is None or rem > 0):
                matches.append(r)
        elif op == "not_updated_for_days":
            u = _parse_date(r.get("updated_at"))
            if u is None or (today - u).days >= val:
                matches.append(r)
    aff = [{"label": _mask_label(r),
            "amount": _num(r.get("remaining_amount_due")) or _num(r.get("current_balance"))} for r in matches]
    return (len(matches) > 0), {"matched": len(matches)}, aff


def evaluate(alert: dict) -> dict:
    """Evaluate all conditions → {state, value, affected, conditions:[...]}.
    Raises AlertError only for unsupported source; missing data yields state=False + note."""
    source = alert["source_type"]
    ctx = resolve(source, alert.get("filters") or {})
    results, values, affected = [], [], []
    for c in alert["conditions"]:
        met, val, aff = _eval_condition(c, ctx)
        results.append(met)
        values.append({"field": c["field"], "operator": c["operator"], "value": c["value"],
                       "evaluated": val, "met": met})
        if met:
            affected = aff or affected
    logical = alert.get("logical_operator", "AND")
    state = all(results) if logical == "AND" else any(results)
    primary = values[0]["evaluated"] if values else None
    if not affected:
        affected = ctx.get("affected", [])[:8]
    return {"state": bool(state), "value": primary, "conditions": values,
            "affected": affected[:8], "scalars": ctx.get("scalars", {})}


# ── notification decision (state-change / cooldown / modes) ───────────────────
def should_notify(alert: dict, new_state: bool, prev_state, last_triggered_at: str | None,
                  now: datetime | None = None) -> bool:
    if not new_state:
        return False
    now = now or _utcnow()
    cooldown = int(alert.get("cooldown_minutes") or 0)
    if cooldown and last_triggered_at:
        lt = None
        try:
            lt = datetime.fromisoformat(last_triggered_at.replace("Z", "+00:00"))
        except ValueError:
            lt = None
        if lt and (now - lt).total_seconds() < cooldown * 60:
            return False
    mode = alert.get("trigger_mode", "state_change")
    if mode == "every_run":
        return True
    if mode == "notify_once":
        return not bool(prev_state) and not last_triggered_at
    if mode == "once_per_day":
        if not last_triggered_at:
            return True
        try:
            lt = datetime.fromisoformat(last_triggered_at.replace("Z", "+00:00"))
            return (now.date() - lt.date()).days >= 1
        except ValueError:
            return True
    # state_change (default): fire only on False→True
    return not bool(prev_state)


# ── human-readable helpers + Slack formatting ────────────────────────────────
_OP_WORDS = {">": "is greater than", ">=": "is at least", "<": "is less than",
             "<=": "is at most", "=": "equals", "!=": "is not",
             "within_days": "is due within", "overdue_by_days": "is overdue by at least",
             "percentage_increase_greater_than": "increased by more than",
             "percentage_decrease_greater_than": "decreased by more than",
             "absolute_change_greater_than": "changed by more than",
             "not_updated_for_days": "has not been updated for"}
_FIELD_WORDS = {"total_current_balance": "Total current balance", "total_due": "Total due",
                "remaining_due": "Remaining due", "minimum_due": "Minimum due",
                "interest": "Interest charged", "credit_card_interest": "Credit-card interest",
                "statement_balance": "Statement balance", "total_assets": "Total assets",
                "total_debt": "Total liabilities", "net_worth": "Net worth",
                "monthly_spend": "Monthly spend", "monthly_income": "Monthly income",
                "category_total": "Category total", "due_date": "A payment",
                "remaining_amount_due": "Remaining amount due", "total_value": "Broker balance",
                "cashflow_metric": "Cash-flow metric"}


def _money(v) -> str:
    if v is None:
        return "—"
    try:
        return f"${float(v):,.0f}"
    except (TypeError, ValueError):
        return str(v)


def describe_condition(cond: dict) -> str:
    field = _FIELD_WORDS.get(cond["field"], cond["field"].replace("_", " "))
    op = _OP_WORDS.get(cond["operator"], cond["operator"])
    val = cond["value"]
    if cond["operator"] in _ROW_OPS:
        unit = "days"
        return f"{field} {op} {int(val)} {unit}"
    if cond["operator"] in ("percentage_increase_greater_than", "percentage_decrease_greater_than"):
        return f"{field} {op} {val:g}%"
    if cond["operator"] == "absolute_change_greater_than":
        return f"{field} {op} {_money(val)}"
    return f"{field} {op} {_money(val)}"


def describe(alert: dict) -> str:
    joiner = " and " if alert.get("logical_operator", "AND") == "AND" else " or "
    return joiner.join(describe_condition(c) for c in alert["conditions"])


def schedule_phrase(schedule: dict) -> str:
    freq = schedule.get("frequency", "daily")
    t = schedule.get("time", "08:00")
    try:
        hh, mm = t.split(":")
        h = int(hh); ap = "AM" if h < 12 else "PM"; h12 = h % 12 or 12
        t = f"{h12}:{mm} {ap}"
    except Exception:  # noqa: BLE001
        pass
    return {"hourly": "Every hour", "daily": f"Every day at {t}", "weekly": f"Every week at {t}",
            "monthly": f"Every month at {t}", "quarterly": f"Every quarter at {t}"}.get(freq, freq)


def slack_message(alert: dict, result: dict, base_url: str = "") -> tuple[str, str, str]:
    """Return (title, mrkdwn_body, severity). No secrets/account numbers ever."""
    title = f"ArtikFinance Alert: {sanitize_text(alert['name'], 120)}"
    lines = [f"*{describe(alert)}*"]
    val = result.get("value")
    if isinstance(val, (int, float)):
        lines.append(f"*Current value:* {_money(val)}")
    thr = alert["conditions"][0]["value"] if alert.get("conditions") else None
    if isinstance(thr, (int, float)) and alert["conditions"][0]["operator"] in _NUMERIC_OPS:
        lines.append(f"*Threshold:* {_money(thr)}")
    lines.append(f"*Triggered:* {datetime.now(timezone.utc).strftime('%b %d, %Y %H:%M UTC')}")
    aff = result.get("affected") or []
    if aff:
        lines.append("*Affected:*")
        for a in aff[:6]:
            amt = a.get("amount")
            lines.append(f"• {sanitize_text(str(a.get('label')), 60)}"
                         + (f": {_money(amt)}" if amt is not None else ""))
    if base_url:
        page = {"payment_accounts": "#payment-apps/overview", "assets": "#assets",
                "liabilities": "#liabilities"}.get(alert["source_type"], "")
        lines.append(f"<{base_url.rstrip('/')}/{page}|View in ArtikFinance>")
    return title, "\n".join(lines), "warning"


def test_message(alert: dict, base_url: str = "") -> tuple[str, str, str]:
    title = f"ArtikFinance Test Alert: {sanitize_text(alert['name'], 120)}"
    body = ("🧪 *This is a test notification.*\n"
            f"Alert: *{sanitize_text(alert['name'], 120)}*\n"
            f"Condition: {describe(alert)}\n"
            f"Destination: {alert['notification'].get('destination') or 'default channel'}\n"
            "Slack delivery is configured successfully.")
    return title, body, "info"
