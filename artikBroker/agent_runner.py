"""Executes a managed agent and captures its result — without blocking the API.

For the Stock News Collector this shells out to the standalone collector
(`news_collector_agent.py --once`) so Broker and the agent stay decoupled and the
exact same code path runs locally and on AWS. A generated JSON config carries the
managed settings (tickers, sources, thresholds); COLLECTOR_DATA_DIR points at the
shared data dir so run_history.jsonl + latest_signals.json land where Broker reads.

Run state is in-memory (per process). Each run also appends to a per-agent log file
so the /logs endpoint can tail it across restarts.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import agents_store as store
from news_runs import latest_run

_LOG_DIR = store.DATA_DIR / "logs"
_state_lock = threading.Lock()
# agent_id -> {"running": bool, "started_at": iso, "run_id": str|None}
_state: dict[str, dict] = {}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_running(agent_id: str) -> bool:
    with _state_lock:
        return _state.get(agent_id, {}).get("running", False)


def state(agent_id: str) -> dict:
    with _state_lock:
        return dict(_state.get(agent_id, {"running": False}))


def _set(agent_id: str, **kw) -> None:
    with _state_lock:
        _state.setdefault(agent_id, {})
        _state[agent_id].update(kw)


def _build_config_file(cfg: dict) -> Path:
    """Write a collector config JSON reflecting the managed settings."""
    payload = {
        "agent_name": cfg.get("agent_name", "Stock News Collector"),
        "enabled": True,
        "tickers": cfg.get("tickers") or [],
        "news_sources": store.enabled_collector_sources(cfg),
        "min_relevance_score": cfg.get("min_relevance_score", 0.70),
        "min_impact_score": cfg.get("min_impact_score", 4),
        "retention_days": cfg.get("retention_days", 90),
        "use_llm": bool(cfg.get("use_llm", True)),
    }
    store.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = store.CONFIG_DIR / f"_collector_{cfg['agent_id']}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _logfile(agent_id: str) -> Path:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    return _LOG_DIR / f"{agent_id}.log"


def tail_log(agent_id: str, lines: int = 200) -> list[str]:
    p = _logfile(agent_id)
    if not p.exists():
        return []
    return p.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]


def _run_blocking(agent_id: str, cfg: dict) -> dict:
    """Invoke the collector once, stream output to the log, return its run record."""
    cfg_path = _build_config_file(cfg)
    tickers = ",".join(cfg.get("tickers") or [])
    cmd = [sys.executable, str(store.COLLECTOR_SCRIPT),
           "--once", "--config", str(cfg_path)]
    if tickers:
        cmd += ["--tickers", tickers]
    if not cfg.get("use_llm", True):
        cmd.append("--no-llm")

    env = {**_inherit_env(),
           "COLLECTOR_DATA_DIR": str(store.DATA_DIR),
           "PYTHONUNBUFFERED": "1"}

    logf = _logfile(agent_id)
    with open(logf, "a", encoding="utf-8") as lf:
        lf.write(f"\n===== run @ {_now()} · tickers={tickers or '(config)'} =====\n")
        lf.flush()
        try:
            proc = subprocess.run(
                cmd, cwd=str(store.COLLECTOR_DIR), env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, timeout=900,
            )
            lf.write(proc.stdout or "")
            lf.write(f"----- exit {proc.returncode} @ {_now()} -----\n")
        except subprocess.TimeoutExpired:
            lf.write("----- TIMEOUT after 900s -----\n")
            return {"status": "failed", "errors": ["timeout after 900s"]}
        except Exception as e:  # noqa: BLE001
            lf.write(f"----- ERROR {e} -----\n")
            return {"status": "failed", "errors": [str(e)]}

    # The collector wrote a run_history record; return the freshest one.
    rec = latest_run(store.DATA_DIR, agent_id)
    return rec or {"status": "partial", "errors": ["no run_history record written"]}


def run_async(agent_id: str, cfg: dict) -> dict:
    """Start a run in a background thread. Returns immediately. No-op if running."""
    if is_running(agent_id):
        return {"started": False, "reason": "already running",
                "state": state(agent_id)}

    started = _now()
    _set(agent_id, running=True, started_at=started, run_id=None,
         last_error=None)

    def _worker():
        try:
            rec = _run_blocking(agent_id, cfg)
            _set(agent_id, running=False, last_record=rec, run_id=rec.get("run_id"),
                 finished_at=_now())
            # Persist last/next run hints on the agent config.
            try:
                store.save_config(agent_id, {"last_run_at": rec.get("completed_at") or started})
            except Exception:  # noqa: BLE001
                pass
        except Exception as e:  # noqa: BLE001
            _set(agent_id, running=False, last_error=str(e), finished_at=_now())

    threading.Thread(target=_worker, name=f"agent-{agent_id}", daemon=True).start()
    return {"started": True, "started_at": started}


def _inherit_env() -> dict:
    import os
    return dict(os.environ)
