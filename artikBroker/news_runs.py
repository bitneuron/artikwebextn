"""Read-side helpers over the collector's local output (run history + results).

Reads the JSONL the standalone collector writes in its data dir. Used by the
Agent Management endpoints for "Last Run Result", View Results, and ticker/source
breakdowns. Read-only; never mutates an Artik Score.
"""
from __future__ import annotations

import json
from pathlib import Path


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def run_history(data_dir: Path, agent_id: str | None = None,
                limit: int = 50) -> list[dict]:
    rows = _read_jsonl(data_dir / "run_history.jsonl")
    if agent_id:
        rows = [r for r in rows if r.get("agent_id") == agent_id]
    rows.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return rows[:limit]


def latest_run(data_dir: Path, agent_id: str | None = None) -> dict | None:
    rows = run_history(data_dir, agent_id, limit=1)
    return rows[0] if rows else None


def results_summary(data_dir: Path, agent_id: str | None = None) -> dict:
    """Latest-run summary + ticker/source breakdown + recent relevant headlines."""
    last = latest_run(data_dir, agent_id)
    classified = _read_jsonl(data_dir / "classified_news.jsonl")
    signals = _read_jsonl(data_dir / "signals.jsonl")
    sig_by_id = {s.get("id"): s for s in signals}

    relevant = [c for c in classified if c.get("relevance") == "RELEVANT"]
    # newest first by published/classified
    relevant.sort(key=lambda c: c.get("classified_at", ""), reverse=True)

    headlines = []
    for c in relevant[:60]:
        sig = sig_by_id.get(c.get("id")) or {}
        headlines.append({
            "ticker": c.get("ticker"),
            "headline": c.get("headline"),
            "source": c.get("source"),
            "relevance": c.get("relevance"),
            "relevance_score": c.get("relevance_score"),
            "sentiment": sig.get("sentiment"),
            "impact_score": sig.get("impact_score"),
            "confidence": sig.get("confidence"),
            "signal_type": sig.get("signal_type"),
            "published": c.get("published"),
            "url": c.get("url"),
        })

    by_ticker: dict[str, int] = {}
    for c in relevant:
        by_ticker[c.get("ticker", "?")] = by_ticker.get(c.get("ticker", "?"), 0) + 1
    by_source: dict[str, int] = {}
    for c in relevant:
        src = (c.get("source", "") or "").split(":")[0] or "unknown"
        by_source[src] = by_source.get(src, 0) + 1

    pos = sum(1 for s in signals if s.get("sentiment") == "positive")
    neg = sum(1 for s in signals if s.get("sentiment") == "negative")

    return {
        "last_run": last,
        "totals": {
            "articles_collected": (last or {}).get("articles_collected"),
            "articles_relevant": (last or {}).get("articles_relevant"),
            "signals_generated": len(signals),
            "signals_positive": pos,
            "signals_negative": neg,
        },
        "by_ticker": by_ticker,
        "by_source": by_source,
        "headlines": headlines,
    }
