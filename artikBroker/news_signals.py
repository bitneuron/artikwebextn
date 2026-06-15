"""Read-side bridge to the standalone news-collector agent.

Artik Broker consumes the agent's `latest_signals.json` overlay artifact. It does
NOT import the agent's code and NEVER mutates an Artik Score — it only reads the
JSON contract the agent publishes and returns an optional overlay the UI shows
*alongside* (never inside) the engine score.

Backend is chosen by environment, mirroring history_store:
  * NEWS_SIGNALS_S3_BUCKET set -> Amazon S3   (AWS; agent + Broker run as separate
                                               containers, S3 is the shared medium)
  * otherwise                  -> local file   (dev; reads the agent's data dir)

The snapshot is cached briefly so per-row analyze calls don't re-hit S3/disk.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Local dev: the agent writes here by default.
_DEFAULT_LOCAL = (
    HERE.parent
    / "artikAgents" / "agents" / "news_collector_agent"
    / "data" / "news_collector" / "latest_signals.json"
)
_LOCAL_PATH = Path(os.environ.get("NEWS_SIGNALS_PATH", str(_DEFAULT_LOCAL)))

_BUCKET = os.environ.get("NEWS_SIGNALS_S3_BUCKET", "").strip()
_KEY = (os.environ.get("NEWS_SIGNALS_S3_KEY", "news_collector/latest_signals.json") or "").strip()
_REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-west-2"

_CACHE_TTL = 60  # seconds
_cache: dict = {"at": 0.0, "data": None}
_s3 = None


def backend() -> str:
    return "s3" if _BUCKET else "local"


def _client():
    global _s3
    if _s3 is None:
        import boto3  # lazy — local dev needs no AWS deps
        _s3 = boto3.client("s3", region_name=_REGION)
    return _s3


def _load_raw() -> dict | None:
    """Load latest_signals.json from the active backend (uncached)."""
    try:
        if _BUCKET:
            obj = _client().get_object(Bucket=_BUCKET, Key=_KEY)
            return json.loads(obj["Body"].read().decode("utf-8"))
        if _LOCAL_PATH.exists():
            return json.loads(_LOCAL_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — never let a missing/broken artifact 500 the app
        return None
    return None


def _snapshot() -> dict | None:
    now = time.time()
    if _cache["data"] is not None and now - _cache["at"] < _CACHE_TTL:
        return _cache["data"]
    data = _load_raw()
    _cache["at"] = now
    _cache["data"] = data
    return data


def available() -> bool:
    """True if a usable signals snapshot exists for the current backend."""
    return _snapshot() is not None


def _is_active(sig: dict, now: datetime) -> bool:
    exp = sig.get("expires_at")
    if not exp:
        return True
    try:
        return datetime.fromisoformat(str(exp).replace("Z", "+00:00")) >= now
    except ValueError:
        return True


def overlay_for(ticker: str) -> dict | None:
    """Return the active overlay for a ticker, or None.

    Shape (subset of the agent's node, defensively re-filtered for expiry):
        {ticker, aggregate_score_delta, net_sentiment, signal_count,
         overlay_cap, signals:[...], note}
    The caller computes `adjusted = base + aggregate_score_delta` itself; this
    module never sees or changes the engine score.
    """
    snap = _snapshot()
    if not snap:
        return None
    node = (snap.get("tickers") or {}).get(ticker.upper())
    if not node:
        return None

    now = datetime.now(timezone.utc)
    active = [s for s in (node.get("signals") or []) if _is_active(s, now)]
    if not active:
        return None

    cap = int(node.get("overlay_cap", snap.get("overlay_cap", 10)) or 10)
    raw_delta = sum(int(s.get("recommended_score_delta", 0) or 0) for s in active)
    agg_delta = max(-cap, min(cap, raw_delta))

    return {
        "ticker": ticker.upper(),
        "aggregate_score_delta": agg_delta,
        "net_sentiment": node.get("net_sentiment", "neutral"),
        "signal_count": len(active),
        "overlay_cap": cap,
        "generated_at": snap.get("generated_at"),
        "note": "Optional news overlay — does NOT modify the Artik Score.",
        "signals": active,
    }


def apply_overlay(row: dict) -> dict:
    """Attach a `news_overlay` to an analyze row in place (if any), without
    touching `row['score']`. Adds `adjusted_score` inside the overlay only.
    Returns the same row for convenience.
    """
    base = row.get("score")
    if base is None:
        return row
    ov = overlay_for(row.get("ticker", ""))
    if not ov:
        return row
    delta = ov["aggregate_score_delta"]
    ov["base_score"] = base
    ov["adjusted_score"] = int(max(0, min(100, base + delta)))
    row["news_overlay"] = ov
    return row
