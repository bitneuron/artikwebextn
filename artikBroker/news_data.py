"""Broker-side cleanup for collector output when a configuration is deleted.

The standalone collector's article/signal storage is SHARED across all collector
configurations (one set of JSONL files per data dir, keyed by ticker — not by
agent). So when a config is deleted we can safely remove:

  • its Broker run-history rows (broker_runs.jsonl, keyed by agent_id)
  • its per-agent log file and generated collector config
  • articles/classified/signals for tickers EXCLUSIVE to it — i.e. tickers no
    longer tracked by any remaining configuration (purging a shared ticker would
    blind other collectors), plus their latest_signals overlay entries.

Everything here is data maintenance over the existing file format; it does not
change the collector code or schema.
"""
from __future__ import annotations

import json
from pathlib import Path

# Filenames kept local so this module has no import dependency on the agent code.
RAW_FILE = "raw_news.jsonl"
CLASSIFIED_FILE = "classified_news.jsonl"
SIGNALS_FILE = "signals.jsonl"
LATEST_FILE = "latest_signals.json"
BROKER_RUNS_FILE = "broker_runs.jsonl"


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


def _rewrite_jsonl(path: Path, rows: list[dict]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")
    tmp.replace(path)


def purge_broker_runs(data_dir: Path, agent_id: str) -> int:
    """Drop the deleted agent's Broker run-history rows. Returns rows removed."""
    path = data_dir / BROKER_RUNS_FILE
    rows = _read_jsonl(path)
    kept = [r for r in rows if r.get("agent_id") != agent_id]
    if len(kept) != len(rows):
        _rewrite_jsonl(path, kept)
    return len(rows) - len(kept)


def delete_logs(data_dir: Path, agent_id: str) -> bool:
    p = data_dir / "logs" / f"{agent_id}.log"
    if p.exists():
        p.unlink()
        return True
    return False


def delete_collector_config(config_dir: Path, agent_id: str) -> bool:
    p = config_dir / f"_collector_{agent_id}.json"
    if p.exists():
        p.unlink()
        return True
    return False


def purge_articles(data_dir: Path, tickers) -> dict:
    """Remove raw/classified/signal rows for the given tickers, and drop them from
    latest_signals.json. Returns counts removed per file."""
    targets = {str(t).strip().upper() for t in (tickers or []) if str(t).strip()}
    removed: dict[str, int] = {}
    if not targets:
        return removed

    for name in (RAW_FILE, CLASSIFIED_FILE, SIGNALS_FILE):
        path = data_dir / name
        rows = _read_jsonl(path)
        if not rows:
            continue
        kept = [r for r in rows if (r.get("ticker") or "").upper() not in targets]
        if len(kept) != len(rows):
            _rewrite_jsonl(path, kept)
            removed[name] = len(rows) - len(kept)

    # latest_signals.json — drop the purged tickers from the overlay snapshot.
    latest = data_dir / LATEST_FILE
    if latest.exists():
        try:
            snap = json.loads(latest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            snap = None
        if isinstance(snap, dict) and isinstance(snap.get("tickers"), dict):
            before = len(snap["tickers"])
            snap["tickers"] = {k: v for k, v in snap["tickers"].items()
                               if k.upper() not in targets}
            if len(snap["tickers"]) != before:
                latest.write_text(json.dumps(snap, indent=2, default=str), encoding="utf-8")
                removed[LATEST_FILE] = before - len(snap["tickers"])
    return removed
