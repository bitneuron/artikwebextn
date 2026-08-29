from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.access import accessible_agent_ids_subquery
from app.auth.deps import get_current_active_user, get_run_or_404, require_agent_access
from app.core.database import get_db
from app.models.agent import Agent
from app.models.run import AgentRun
from app.models.run_log import RunLog
from app.models.user import User
from app.schemas.run import RunLogOut, RunOut
from app.services.run_service import run_to_out

router = APIRouter(tags=["runs"])


@router.get("/api/agents/{agent_id}/runs", response_model=list[RunOut])
def list_agent_runs(agent_id: int, db: Session = Depends(get_db),
                    agent: Agent = Depends(require_agent_access("viewer")),
                    limit: int = Query(50, le=200), offset: int = 0):
    stmt = (select(AgentRun).where(AgentRun.agent_id == agent_id)
           .order_by(AgentRun.created_at.desc()).limit(limit).offset(offset))
    return [run_to_out(r) for r in db.execute(stmt).scalars().all()]


@router.get("/api/runs", response_model=list[RunOut])
def list_all_runs(
    db: Session = Depends(get_db), user: User = Depends(get_current_active_user),
    status: str | None = None, trigger: str | None = None,
    limit: int = Query(100, le=500), offset: int = 0,
):
    accessible = accessible_agent_ids_subquery(db, user)
    stmt = select(AgentRun).where(AgentRun.agent_id.in_(accessible))
    if status:
        stmt = stmt.where(AgentRun.status == status)
    if trigger:
        stmt = stmt.where(AgentRun.trigger == trigger)
    stmt = stmt.order_by(AgentRun.created_at.desc()).limit(limit).offset(offset)
    return [run_to_out(r) for r in db.execute(stmt).scalars().all()]


@router.get("/api/runs/{run_id}", response_model=RunOut)
def get_run(db: Session = Depends(get_db), run: AgentRun = Depends(get_run_or_404("viewer"))):
    return run_to_out(run)


@router.get("/api/runs/{run_id}/logs", response_model=list[RunLogOut])
def get_run_logs(db: Session = Depends(get_db), run: AgentRun = Depends(get_run_or_404("viewer"))):
    stmt = select(RunLog).where(RunLog.run_id == run.id).order_by(RunLog.ts.asc())
    return list(db.execute(stmt).scalars().all())
