from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.access import accessible_agent_ids_subquery
from app.auth.deps import get_current_active_user
from app.core.database import get_db
from app.models.agent import Agent
from app.models.alert import AlertEvent
from app.models.result import Result
from app.models.user import User
from app.schemas.alert import AlertEventOut, DashboardOut

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut)
def get_dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    from app.scheduler.scheduler import is_running

    since = datetime.now(timezone.utc) - timedelta(days=7)
    accessible = accessible_agent_ids_subquery(db, user)

    def count_status(status: str) -> int:
        return db.execute(
            select(func.count()).select_from(Agent)
            .where(Agent.status == status, Agent.id.in_(accessible))
        ).scalar_one()

    new_findings = db.execute(
        select(func.count()).select_from(Result)
        .where(Result.created_at >= since, Result.agent_id.in_(accessible))
    ).scalar_one()
    high_priority = db.execute(
        select(func.count()).select_from(Result)
        .where(Result.priority_flag.is_(True), Result.is_dismissed.is_(False), Result.agent_id.in_(accessible))
    ).scalar_one()
    recent_alerts = list(db.execute(
        select(AlertEvent).where(AlertEvent.agent_id.in_(accessible))
        .order_by(AlertEvent.created_at.desc()).limit(10)
    ).scalars().all())

    return {
        "total_agents": count_status("active") + count_status("paused"),
        "active_agents": count_status("active"),
        "paused_agents": count_status("paused"),
        "error_agents": db.execute(
            select(func.count()).select_from(Agent)
            .where(Agent.last_run_status == "failed", Agent.id.in_(accessible))
        ).scalar_one(),
        "new_findings_7d": new_findings,
        "high_priority_alerts": high_priority,
        "sources_checked_7d": 0,
        "upcoming_deadlines": 0,
        "scheduler_running": is_running(),
        "recent_alerts": [AlertEventOut.model_validate(a, from_attributes=True) for a in recent_alerts],
    }
