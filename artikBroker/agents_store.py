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
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Shared data dir with the standalone collector (so the subprocess, news_signals.py,
# and run-history all line up). Overridable for tests/containers.
DATA_DIR = Path(os.environ.get(
    "NEWS_COLLECTOR_DATA_DIR",
    str(HERE.parent / "artikAgents" / "agents" / "news_collector_agent"
        / "data" / "news_collector"),
))
COLLECTOR_DIR = HERE.parent / "artikAgents" / "agents" / "news_collector_agent"
COLLECTOR_SCRIPT = COLLECTOR_DIR / "news_collector_agent.py"

CONFIG_DIR = HERE / "config"
CONFIG_PATH = CONFIG_DIR / "agent_schedules.json"

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
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_all(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(CONFIG_PATH)


def _merged_config(agent_id: str, stored: dict) -> dict:
    """Registry defaults overlaid with any stored config for one agent."""
    reg = REGISTRY[agent_id]
    cfg = dict(reg["defaults"])
    cfg.update(stored.get(agent_id, {}))
    # Ensure every catalog source has an explicit enabled flag.
    src = dict(default_sources())
    src.update(cfg.get("sources") or {})
    cfg["sources"] = {k: bool(v) for k, v in src.items() if k in _SRC_BY_ID}
    cfg.update({
        "agent_id": agent_id,
        "agent_name": reg["agent_name"],
        "agent_type": reg["agent_type"],
        "description": cfg.get("description") or reg["description"],
    })
    return cfg


def get_config(agent_id: str) -> dict | None:
    if agent_id not in REGISTRY:
        return None
    with _lock:
        return _merged_config(agent_id, _read_all())


def save_config(agent_id: str, patch: dict) -> dict:
    """Merge a partial update into an agent's stored config and persist it."""
    if agent_id not in REGISTRY:
        raise KeyError(agent_id)
    with _lock:
        data = _read_all()
        cur = data.get(agent_id, {})
        cur.update({k: v for k, v in patch.items() if k in REGISTRY[agent_id]["defaults"]
                    or k == "description"})
        if "sources" in patch and isinstance(patch["sources"], dict):
            merged = dict(default_sources())
            merged.update(cur.get("sources") or {})
            merged.update(patch["sources"])
            cur["sources"] = {k: bool(v) for k, v in merged.items() if k in _SRC_BY_ID}
        data[agent_id] = cur
        _write_all(data)
        return _merged_config(agent_id, data)


def delete_config(agent_id: str) -> None:
    with _lock:
        data = _read_all()
        if agent_id in data:
            del data[agent_id]
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
