"""APScheduler-based background scheduler. Runs the due-notification dispatch on an
interval (default hourly per spec). Designed to be swapped for AWS EventBridge →
Lambda later: the actual work lives in services.notification_service.dispatch_due,
which the same way a Lambda handler would call."""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging_config import log_event
from app.services.notification_service import dispatch_due

_scheduler: BackgroundScheduler | None = None


def _tick() -> None:
    db = SessionLocal()
    try:
        dispatch_due(db)
    except Exception as e:  # noqa: BLE001
        log_event("error", "scheduler tick crashed", error=str(e))
    finally:
        db.close()


def start_scheduler() -> None:
    global _scheduler
    if not settings.scheduler_enabled or _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC", daemon=True)
    _scheduler.add_job(_tick, "interval", minutes=settings.scheduler_interval_minutes,
                       id="dispatch_due", next_run_time=None, max_instances=1, coalesce=True)
    _scheduler.start()
    log_event("scheduler", "started", interval_minutes=settings.scheduler_interval_minutes)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def run_once() -> dict:
    """Manual trigger (admin/health/testing)."""
    db = SessionLocal()
    try:
        return dispatch_due(db)
    finally:
        db.close()
