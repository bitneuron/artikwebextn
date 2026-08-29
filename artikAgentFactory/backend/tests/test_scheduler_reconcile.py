from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

import app.scheduler.scheduler as sched_mod
from app.scheduler.scheduler import _trigger_for, unschedule_agent


def test_trigger_for_manual_mode_returns_none():
    assert _trigger_for({"mode": "manual"}) is None


def test_trigger_for_interval_mode_does_not_fire_immediately():
    trigger = _trigger_for({"mode": "interval", "interval_minutes": 30})
    assert isinstance(trigger, IntervalTrigger)
    # first fire must be pushed out ~30 min, not "now" (IntervalTrigger fires
    # immediately by default otherwise — this is the exact bug that got caught live)
    from datetime import datetime, timedelta, timezone
    assert trigger.start_date > datetime.now(timezone.utc) + timedelta(minutes=25)


def test_trigger_for_preset_mode_returns_cron():
    trigger = _trigger_for({"mode": "preset", "preset": "daily", "hour_utc": 3})
    assert isinstance(trigger, CronTrigger)


def test_add_replace_remove_job_cycle():
    sched_mod._scheduler = BackgroundScheduler(timezone="UTC", daemon=True)
    sched_mod._scheduler.start()
    try:
        sched_mod._add_job(999, {"mode": "interval", "interval_minutes": 15})
        assert sched_mod._scheduler.get_job("agent-999") is not None

        sched_mod._add_job(999, {"mode": "preset", "preset": "daily", "hour_utc": 5})
        job = sched_mod._scheduler.get_job("agent-999")
        assert isinstance(job.trigger, CronTrigger)

        unschedule_agent(999)
        assert sched_mod._scheduler.get_job("agent-999") is None
    finally:
        sched_mod._scheduler.shutdown(wait=False)
        sched_mod._scheduler = None


def test_reschedule_agent_removes_job_when_agent_paused(db_session):
    from app.models.agent import Agent
    from app.models.user import User
    from app.models.workspace import Workspace

    ws = Workspace(name="Test", slug="test-ws-sched")
    db_session.add(ws)
    db_session.flush()
    owner = User(email="sched@test.local", username="sched", password_hash="x",
                role="administrator", workspace_id=ws.id)
    db_session.add(owner)
    db_session.flush()
    agent = Agent(template_id="general_research", name="t", objective="o", status="paused",
                 owner_id=owner.id, workspace_id=ws.id,
                 schedule_json='{"mode":"interval","interval_minutes":30}', is_schedule_enabled=True)
    db_session.add(agent)
    db_session.commit()

    sched_mod._scheduler = BackgroundScheduler(timezone="UTC", daemon=True)
    sched_mod._scheduler.start()
    try:
        sched_mod._add_job(agent.id, {"mode": "interval", "interval_minutes": 30})
        assert sched_mod._scheduler.get_job(f"agent-{agent.id}") is not None

        sched_mod.reschedule_agent(agent.id)  # agent is paused -> should be removed, not (re)added
        assert sched_mod._scheduler.get_job(f"agent-{agent.id}") is None
    finally:
        sched_mod._scheduler.shutdown(wait=False)
        sched_mod._scheduler = None
