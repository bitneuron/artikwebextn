"""Scheduling abstraction for managed agents.

`AgentScheduler` is the interface; swap the implementation without touching the
API or UI. `LocalAgentScheduler` runs an in-process daemon thread (no extra deps)
that fires due agents and persists next_run_at. `AwsAgentScheduler` is a
documented stub: on AWS the firing is owned by EventBridge → ECS/Lambda, so the
in-process loop is disabled and next-run is computed for display only.

Select via env AGENT_SCHEDULER = "local" (default) | "aws" | "off".
"""
from __future__ import annotations

import os
import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

import agents_store as store

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

_UNIT_SECONDS = {"minute": 60, "hour": 3600, "day": 86400}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def compute_next_run(cfg: dict, now: datetime | None = None) -> str:
    """Next run time (UTC ISO 'Z') from an agent's schedule config."""
    now = now or _utc_now()
    stype = cfg.get("schedule_type", "interval")

    if stype == "daily_time":
        tzname = cfg.get("timezone") or store.DEFAULT_TZ
        tz = ZoneInfo(tzname) if ZoneInfo else timezone.utc
        hh, _, mm = (cfg.get("daily_time") or "18:00").partition(":")
        try:
            hh, mm = int(hh), int(mm or 0)
        except ValueError:
            hh, mm = 18, 0
        local_now = now.astimezone(tz)
        target = local_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target <= local_now:
            target += timedelta(days=1)
        return _iso(target)

    # interval
    val = max(1, int(cfg.get("interval_value", 1) or 1))
    unit = cfg.get("interval_unit", "hour")
    secs = val * _UNIT_SECONDS.get(unit, 3600)
    return _iso(now + timedelta(seconds=secs))


class AgentScheduler(ABC):
    """Trigger managed agents on their configured schedule."""

    def __init__(self, runner):
        self.runner = runner

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def backend(self) -> str: ...

    def ensure_next_run(self, cfg: dict) -> dict:
        """Compute + persist next_run_at when enabled and missing."""
        if cfg.get("enabled") and not cfg.get("next_run_at"):
            nxt = compute_next_run(cfg)
            cfg = store.save_config(cfg["agent_id"], {"next_run_at": nxt})
        return cfg


class LocalAgentScheduler(AgentScheduler):
    """In-process daemon thread. Fine for a single uvicorn worker / App Runner."""

    TICK_SECONDS = 30

    def __init__(self, runner):
        super().__init__(runner)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def backend(self) -> str:
        return "local"

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="agent-scheduler",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        # Seed next_run for already-enabled agents at boot.
        for aid in store.all_agent_ids():
            try:
                self.ensure_next_run(store.get_config(aid))
            except Exception:  # noqa: BLE001
                pass
        while not self._stop.wait(self.TICK_SECONDS):
            try:
                self._tick()
            except Exception:  # noqa: BLE001 — a bad tick must not kill the loop
                pass

    def _tick(self) -> None:
        now = _utc_now()
        for aid in store.all_agent_ids():
            cfg = store.get_config(aid)
            if not cfg or not cfg.get("enabled"):
                continue
            cfg = self.ensure_next_run(cfg)
            nxt = _parse_iso(cfg.get("next_run_at"))
            if nxt and nxt <= now and not self.runner.is_running(aid):
                self.runner.run_async(aid, cfg, trigger_source="scheduled")
                # schedule the following run from now
                store.save_config(aid, {"next_run_at": compute_next_run(cfg, now)})


class AwsAgentScheduler(AgentScheduler):
    """No in-process loop — EventBridge → ECS/Lambda owns firing on AWS.

    next_run_at is still computed for display; triggering is external. See
    artikAgents/agents/news_collector_agent/DEPLOY_AWS.md.
    """

    def backend(self) -> str:
        return "aws"

    def start(self) -> None:
        for aid in store.all_agent_ids():
            try:
                self.ensure_next_run(store.get_config(aid))
            except Exception:  # noqa: BLE001
                pass

    def stop(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Singleton wiring
# ---------------------------------------------------------------------------
_scheduler: AgentScheduler | None = None


def get_scheduler():
    global _scheduler
    if _scheduler is None:
        import agent_runner
        mode = (os.environ.get("AGENT_SCHEDULER") or "local").strip().lower()
        if mode == "aws":
            _scheduler = AwsAgentScheduler(agent_runner)
        elif mode == "off":
            _scheduler = _NullScheduler(agent_runner)
        else:
            _scheduler = LocalAgentScheduler(agent_runner)
    return _scheduler


class _NullScheduler(AgentScheduler):
    def backend(self) -> str:
        return "off"

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass
