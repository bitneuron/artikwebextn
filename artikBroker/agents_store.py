"""Agent registry + persisted configuration for the Agent Management page.

- A static REGISTRY describes the agents Broker knows how to manage (currently the
  Stock News Collector) and the trusted-source catalog with trust tiers/scores.
- Per-agent config (schedule, tickers, sources, classification thresholds) persists
  to config/agent_schedules.json — the local-first store the spec asks for.
- list_agents() merges registry + config + live state (last run from the collector's
  run_history.jsonl, next run from the schedule, running flag from the runner).

This module owns NO scheduling or execution — agent_scheduler.py and agent_runner.py
do. It also never touches Artik Scores.
"""
from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Every managed config is an *instance* of a registry template. The default
# instance shares its id with the template; cloned/added instances get derived ids.
BASE_TEMPLATE = "stock_news_collector"

# Reserved keys inside agent_schedules.json that are not agent instances.
# __deleted__ tombstones registry-default ids the user explicitly deleted, so the
# default collector can be removed entirely (re-creatable via "Add Configuration").
_DELETED_KEY = "__deleted__"
_RESERVED = {_DELETED_KEY}

# Shared data dir with the standalone collector (so the subprocess, news_signals.py,
# and run-history all line up). Overridable for tests/containers.
# Collector location is env-overridable so the agent works both in local dev (sibling
# artikAgents/ checkout) and in the Broker Docker image (collector baked at NEWS_COLLECTOR_DIR).
COLLECTOR_DIR = Path(os.environ.get(
    "NEWS_COLLECTOR_DIR",
    str(HERE.parent / "artikAgents" / "agents" / "news_collector_agent"),
))
COLLECTOR_SCRIPT = Path(os.environ.get(
    "NEWS_COLLECTOR_SCRIPT", str(COLLECTOR_DIR / "news_collector_agent.py")))
DATA_DIR = Path(os.environ.get(
    "NEWS_COLLECTOR_DATA_DIR", str(COLLECTOR_DIR / "data" / "news_collector"),
))

CONFIG_DIR = HERE / "config"
CONFIG_PATH = CONFIG_DIR / "agent_schedules.json"

# Durable persistence: the agent config is stored in the SAME SQLite DB as users
# (USERS_DB_PATH), which Litestream replicates to S3 — so the News Collector's enabled
# state, tracked tickers and schedule SURVIVE App Runner redeploys. The JSON file is kept
# only as a local cache / dev fallback (it lives on the ephemeral /app/config).
import sqlite3  # noqa: E402
_DB_PATH = Path(os.environ.get("USERS_DB_PATH", str(CONFIG_DIR / "users.db")))
_KV_KEY = "agent_schedules"


def _db_conn():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(_DB_PATH), timeout=10, check_same_thread=False)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=5000")
    c.execute("CREATE TABLE IF NOT EXISTS app_kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    return c


def _db_get():
    """Parsed agent config from the durable DB, or None if never written / unavailable."""
    try:
        with _db_conn() as c:
            row = c.execute("SELECT value FROM app_kv WHERE key=?", (_KV_KEY,)).fetchone()
        return json.loads(row[0]) if row else None
    except Exception:  # noqa: BLE001
        return None


def _db_set(data: dict) -> bool:
    try:
        with _db_conn() as c:
            c.execute("INSERT INTO app_kv (key, value) VALUES (?,?) "
                      "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                      (_KV_KEY, json.dumps(data)))
        return True
    except Exception:  # noqa: BLE001
        return False


DEFAULT_TZ = os.environ.get("TZ") or "America/Los_Angeles"

_lock = threading.RLock()


# ---------------------------------------------------------------------------
# Trusted-source catalog (tiers + trust scores). `impl` marks sources the
# collector can actually fetch today; the rest are shown for configuration and
# are on the roadmap (honest: toggling them won't change collection yet).
# ---------------------------------------------------------------------------
SOURCE_CATALOG = [
    # Tier 1 — primary filings / issuer
    {"id": "sec_edgar", "name": "SEC EDGAR", "tier": 1, "trust": 0.99, "impl": False},
    {"id": "company_ir", "name": "Company Investor Relations", "tier": 1, "trust": 0.97, "impl": False},
    {"id": "press_releases", "name": "Company Press Releases", "tier": 1, "trust": 0.95, "impl": False},
    # Tier 2 — top-tier wires / papers
    {"id": "reuters", "name": "Reuters", "tier": 2, "trust": 0.93, "impl": True, "src": "reuters"},
    {"id": "bloomberg", "name": "Bloomberg", "tier": 2, "trust": 0.93, "impl": False},
    {"id": "wsj", "name": "Wall Street Journal", "tier": 2, "trust": 0.91, "impl": True, "src": "wsj"},
    {"id": "ft", "name": "Financial Times", "tier": 2, "trust": 0.90, "impl": False},
    # Tier 3 — data vendors
    {"id": "finnhub", "name": "Finnhub", "tier": 3, "trust": 0.85, "impl": False},
    {"id": "av_news", "name": "Alpha Vantage News Sentiment", "tier": 3, "trust": 0.84, "impl": False},
    {"id": "fmp", "name": "Financial Modeling Prep", "tier": 3, "trust": 0.82, "impl": False},
    # Tier 4 — mainstream finance media
    {"id": "yfinance", "name": "Yahoo Finance", "tier": 4, "trust": 0.74, "impl": True, "src": "yfinance"},
    {"id": "google_news", "name": "Google News (aggregator)", "tier": 4, "trust": 0.72, "impl": True, "src": "google_news"},
    {"id": "cnbc", "name": "CNBC", "tier": 4, "trust": 0.71, "impl": True, "src": "cnbc"},
    {"id": "marketwatch", "name": "MarketWatch", "tier": 4, "trust": 0.70, "impl": False},
    {"id": "barrons", "name": "Barron's", "tier": 4, "trust": 0.70, "impl": False},
    {"id": "bbc", "name": "BBC Business", "tier": 4, "trust": 0.70, "impl": True, "src": "bbc"},
    # Tier 5 — social / sentiment
    {"id": "reddit", "name": "Reddit", "tier": 5, "trust": 0.55, "impl": False},
    {"id": "x_twitter", "name": "X / Twitter", "tier": 5, "trust": 0.52, "impl": False},
    {"id": "stocktwits", "name": "StockTwits", "tier": 5, "trust": 0.50, "impl": False},
]
_SRC_BY_ID = {s["id"]: s for s in SOURCE_CATALOG}
_IMPL_DEFAULT_ON = {"yfinance", "google_news"}  # sane default enabled set


def default_sources() -> dict:
    """source_id -> enabled. Implemented defaults on; everything else off."""
    return {s["id"]: (s["id"] in _IMPL_DEFAULT_ON) for s in SOURCE_CATALOG}


# ---------------------------------------------------------------------------
# Registry — agents Broker can manage, with their built-in defaults.
# ---------------------------------------------------------------------------
REGISTRY = {
    "stock_news_collector": {
        "agent_id": "stock_news_collector",
        "agent_name": "Stock News Collector",
        "agent_type": "News Intelligence",
        "description": "Collects trusted news for selected stocks, classifies "
                       "relevance, extracts signals, and stores results that Artik "
                       "Broker can optionally overlay on the score.",
        "defaults": {
            "enabled": False,
            "schedule_type": "interval",
            "interval_value": 1,
            "interval_unit": "hour",
            "daily_time": "18:00",
            "timezone": DEFAULT_TZ,
            # Plain-English statement (like AI Search). When set, it is resolved to
            # `tickers` via nl_tickers; the resolved list is what actually gets collected.
            "query": "",
            "tickers": ["NVDA", "AVGO", "TSM", "AMD"],
            "sources": default_sources(),
            "min_relevance_score": 0.70,
            "min_impact_score": 4,
            "retention_days": 90,
            "dedup": True,
            "use_llm": True,
            "last_run_at": None,
            "next_run_at": None,
        },
    },
}


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _read_all() -> dict:
    # Durable DB first (survives redeploys). Fall back to the legacy JSON file and
    # migrate it into the DB, so existing configs are picked up transparently.
    db = _db_get()
    if db is not None:
        return db
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) or {}
        except (json.JSONDecodeError, OSError):
            data = {}
        if data:
            _db_set(data)   # migrate legacy file → durable DB (one-time)
        return data
    return {}


def _write_all(data: dict) -> None:
    _db_set(data)   # durable: Litestream replicates the users DB to S3
    try:            # local cache / dev fallback (ephemeral on AWS)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        tmp = CONFIG_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(CONFIG_PATH)
    except OSError:
        pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _template_of(agent_id: str, stored: dict) -> str:
    """Which registry template an instance derives from."""
    t = (stored.get(agent_id) or {}).get("template")
    if t in REGISTRY:
        return t
    return agent_id if agent_id in REGISTRY else BASE_TEMPLATE


def _deleted_set(stored: dict) -> set[str]:
    return set(stored.get(_DELETED_KEY) or [])


def all_agent_ids(stored: dict | None = None) -> list[str]:
    """Every manageable agent id: registry defaults first, then stored instances.
    Registry ids the user deleted (tombstoned) are omitted."""
    data = _read_all() if stored is None else stored
    deleted = _deleted_set(data)
    ids = [r for r in REGISTRY if r not in deleted]
    extras = [aid for aid in data if aid not in REGISTRY and aid not in _RESERVED]
    extras.sort(key=lambda a: ((data[a] or {}).get("created_at", ""), a))
    return ids + extras


def _exists(agent_id: str, stored: dict) -> bool:
    if agent_id in _RESERVED:
        return False
    if agent_id in REGISTRY:
        return agent_id not in _deleted_set(stored)
    return agent_id in stored


def _merged_config(agent_id: str, stored: dict) -> dict:
    """Template defaults overlaid with any stored config for one instance."""
    reg = REGISTRY[_template_of(agent_id, stored)]
    cfg = dict(reg["defaults"])
    cfg.update(stored.get(agent_id, {}))
    # Ensure every catalog source has an explicit enabled flag.
    src = dict(default_sources())
    src.update(cfg.get("sources") or {})
    cfg["sources"] = {k: bool(v) for k, v in src.items() if k in _SRC_BY_ID}
    # Description falls back to the template's only when not explicitly set (a
    # blank-created config stores "" and must stay blank).
    raw_desc = cfg.get("description")
    cfg.update({
        "agent_id": agent_id,
        "agent_name": cfg.get("agent_name") or reg["agent_name"],
        "agent_type": reg["agent_type"],
        "description": reg["description"] if raw_desc is None else raw_desc,
    })
    return cfg


def get_config(agent_id: str) -> dict | None:
    with _lock:
        data = _read_all()
        if not _exists(agent_id, data):
            return None
        return _merged_config(agent_id, data)


def save_config(agent_id: str, patch: dict) -> dict:
    """Merge a partial update into an instance's stored config and persist it."""
    with _lock:
        data = _read_all()
        if not _exists(agent_id, data):
            raise KeyError(agent_id)
        tmpl = _template_of(agent_id, data)
        cur = data.get(agent_id, {})
        allowed = set(REGISTRY[tmpl]["defaults"]) | {"description", "agent_name", "template"}
        cur.update({k: v for k, v in patch.items() if k in allowed})
        if "sources" in patch and isinstance(patch["sources"], dict):
            merged = dict(default_sources())
            merged.update(cur.get("sources") or {})
            merged.update(patch["sources"])
            cur["sources"] = {k: bool(v) for k, v in merged.items() if k in _SRC_BY_ID}
        data[agent_id] = cur
        _write_all(data)
        return _merged_config(agent_id, data)


def create_instance(agent_name: str | None = None, clone_from: str | None = None,
                    template: str = BASE_TEMPLATE) -> dict:
    """Create a new managed config instance, optionally cloned from another."""
    with _lock:
        data = _read_all()
        base = template if template in REGISTRY else BASE_TEMPLATE
        if clone_from and _exists(clone_from, data):
            base = _template_of(clone_from, data)
        cloning = bool(clone_from and _exists(clone_from, data))
        name = (agent_name or "").strip() or (
            (_merged_config(clone_from, data)["agent_name"] + " (copy)")
            if cloning else "New Collector")
        slug = (re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:24]) or "collector"
        aid = f"{base}__{slug}-{uuid.uuid4().hex[:4]}"
        entry: dict = {"template": base, "agent_name": name,
                       "created_at": _now_iso(), "enabled": False}
        if cloning:
            src = _merged_config(clone_from, data)
            for k in REGISTRY[base]["defaults"]:
                if k not in ("last_run_at", "next_run_at"):
                    entry[k] = src.get(k)
            entry["description"] = src.get("description")
            entry["enabled"] = False
        else:
            # Blank new configuration — never inherit default/other-agent tickers.
            entry["tickers"] = []
            entry["query"] = ""
            entry["description"] = ""
        data[aid] = entry
        _write_all(data)
        return _merged_config(aid, data)


def tracked_tickers(exclude: str | None = None) -> set[str]:
    """Union of tickers tracked across all instances (optionally excluding one).

    Used before purging a deleted config's data so we never remove articles for a
    ticker another collector still tracks."""
    with _lock:
        data = _read_all()
        out: set[str] = set()
        for aid in all_agent_ids(data):
            if aid == exclude:
                continue
            cfg = _merged_config(aid, data)
            out.update((t or "").upper() for t in (cfg.get("tickers") or []) if t)
        return out


def delete_config(agent_id: str) -> None:
    """Remove an agent entirely. A derived instance disappears; a registry-default
    id is tombstoned so it no longer appears (re-creatable via Add Configuration)."""
    with _lock:
        data = _read_all()
        changed = False
        if agent_id in data:
            del data[agent_id]
            changed = True
        if agent_id in REGISTRY:
            deleted = _deleted_set(data)
            if agent_id not in deleted:
                deleted.add(agent_id)
                data[_DELETED_KEY] = sorted(deleted)
                changed = True
        if changed:
            _write_all(data)


# ---------------------------------------------------------------------------
# Source → collector mapping
# ---------------------------------------------------------------------------

def enabled_collector_sources(cfg: dict) -> list[str]:
    """The collector `news_sources` list: enabled AND implemented catalog sources."""
    out = []
    for sid, on in (cfg.get("sources") or {}).items():
        s = _SRC_BY_ID.get(sid)
        if on and s and s.get("impl") and s.get("src"):
            out.append(s["src"])
    return out or ["yfinance", "google_news"]  # never collect from nothing


def source_catalog_view(cfg: dict) -> list[dict]:
    """Catalog enriched with the agent's enabled flags, for the Edit modal."""
    src = cfg.get("sources") or {}
    return [{**s, "enabled": bool(src.get(s["id"], False))} for s in SOURCE_CATALOG]
