"""APScheduler-based per-agent background scheduler. Jobs are rebuilt from the `agents`
table on startup (no separate job persistence needed — the table is the source of
truth). Agent create/edit/delete call reschedule_agent/unschedule_agent so the running
job set always matches each agent's current schedule_json."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging_config import log_event
from app.core.utils import from_json

_scheduler: BackgroundScheduler | None = None

_PRESET_CRON = {
    "daily": {"day": "*"},
    "weekly": {"day_of_week": "mon"},
    "biweekly": {"day_of_week": "mon,thu"},
    "monthly": {"day": "1"},
}


def _job_id(agent_id: int) -> str:
    return f"agent-{agent_id}"


def _run_agent_job(agent_id: int) -> None:
    from app.models.agent import Agent
    from app.services.run_service import execute_run

    db = SessionLocal()
    try:
        agent = db.get(Agent, agent_id)
        if agent and agent.status == "active":
            execute_run(db, agent, trigger="scheduled")
    except Exception as e:  # noqa: BLE001 — the scheduler thread must never die
        log_event("scheduler", "scheduled run crashed", level=logging.ERROR, agent_id=agent_id, error=str(e))
    finally:
        db.close()


def _trigger_for(schedule: dict):
    mode = schedule.get("mode", "manual")
    if mode == "interval":
        minutes = max(15, int(schedule.get("interval_minutes") or 60))
        # IntervalTrigger fires immediately on creation unless start_date is pushed out —
        # first run should be one interval from now, not the moment the schedule is saved.
        first_run = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        return IntervalTrigger(minutes=minutes, start_date=first_run)
    if mode == "preset":
        preset = schedule.get("preset", "weekly")
        hour = int(schedule.get("hour_utc") if schedule.get("hour_utc") is not None else 9)
        cron_kwargs = dict(_PRESET_CRON.get(preset, _PRESET_CRON["weekly"]))
        return CronTrigger(hour=hour, minute=0, timezone="UTC", **cron_kwargs)
    return None


def start_scheduler() -> None:
    global _scheduler
    if not settings.scheduler_enabled or _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC", daemon=True)
    _scheduler.start()
    log_event("scheduler", "started")

    from app.repositories.agent_repo import AgentRepository
    db = SessionLocal()
    try:
        for agent in AgentRepository(db).active_scheduled():
            _add_job(agent.id, from_json(agent.schedule_json, {"mode": "manual"}))
    finally:
        db.close()


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def is_running() -> bool:
    return _scheduler is not None and _scheduler.running


def _add_job(agent_id: int, schedule: dict) -> None:
    if _scheduler is None:
        return
    trigger = _trigger_for(schedule)
    if trigger is None:
        return
    _scheduler.add_job(_run_agent_job, trigger, id=_job_id(agent_id), args=[agent_id],
                       max_instances=1, coalesce=True, replace_existing=True)


def reschedule_agent(agent_id: int) -> None:
    """Call after create/update — reads the agent's current schedule_json fresh and
    replaces (or removes) its job accordingly."""
    if _scheduler is None:
        return
    from app.core.database import SessionLocal as _SL
    from app.models.agent import Agent

    db = _SL()
    try:
        agent = db.get(Agent, agent_id)
        if not agent or agent.status != "active" or not agent.is_schedule_enabled:
            unschedule_agent(agent_id)
            return
        _add_job(agent_id, from_json(agent.schedule_json, {"mode": "manual"}))
    finally:
        db.close()


def unschedule_agent(agent_id: int) -> None:
    if _scheduler is None:
        return
    job_id = _job_id(agent_id)
    if _scheduler.get_job(job_id):
        _scheduler.remove_job(job_id)
