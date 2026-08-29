from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.auth.access import accessible_agent_ids_subquery, effective_level
from app.auth.audit import record_audit
from app.auth.deps import get_current_active_user, require_agent_access, require_role
from app.core.database import get_db
from app.models.agent import Agent
from app.models.user import User
from app.schemas.agent import AgentCreate, AgentOut, AgentUpdate
from app.schemas.common import Message
from app.schemas.run import RunOut
from app.services.agent_service import AgentNotFound, AgentService, UnknownTemplate

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _svc(db: Session) -> AgentService:
    return AgentService(db)


@router.get("")
def list_agents(
    db: Session = Depends(get_db), user: User = Depends(get_current_active_user),
    status: str | None = None, template_id: str | None = None,
    search: str | None = None, sort: str = "updated_at", order: str = "desc",
    limit: int = Query(200, le=500), offset: int = 0,
):
    svc = _svc(db)
    accessible = accessible_agent_ids_subquery(db, user)
    rows = svc.list(accessible_ids=accessible, status=status, template_id=template_id, search=search,
                    sort=sort, order=order, limit=limit, offset=offset)
    out = []
    for a in rows:
        level = effective_level(db, user, a)
        out.append(svc.to_list_item(a, can_manage=level >= 3, can_run=level >= 2))
    return out


@router.post("", response_model=AgentOut, status_code=201)
def create_agent(body: AgentCreate, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(require_role("administrator", "agent_manager"))):
    svc = _svc(db)
    try:
        agent = svc.create(body, owner_id=user.id, workspace_id=user.workspace_id)
    except UnknownTemplate as e:
        raise HTTPException(400, f"unknown template: {e}")
    record_audit(db, actor=user, action="agent.create", resource_type="agent",
                resource_id=agent.id, outcome="success", request=request,
                metadata={"template_id": agent.template_id, "name": agent.name})
    db.commit()
    if body.run_immediately:
        from app.services.run_service import execute_run
        try:
            execute_run(db, agent, trigger="manual")
        except Exception:  # noqa: BLE001 — creation must still succeed even if the first run fails
            pass
    from app.scheduler.scheduler import reschedule_agent
    reschedule_agent(agent.id)
    return svc.to_out(agent)


@router.get("/{agent_id}", response_model=AgentOut)
def get_agent(agent_id: int, db: Session = Depends(get_db), agent: Agent = Depends(require_agent_access("viewer"))):
    return _svc(db).to_out(agent)


@router.put("/{agent_id}", response_model=AgentOut)
def update_agent(agent_id: int, body: AgentUpdate, request: Request, db: Session = Depends(get_db),
                 agent: Agent = Depends(require_agent_access("manager")),
                 user: User = Depends(get_current_active_user)):
    svc = _svc(db)
    touched = body.model_dump(exclude_unset=True)
    schedule_touched = "schedule" in touched or "is_schedule_enabled" in touched or "status" in touched
    try:
        agent = svc.update(agent_id, body)
    except AgentNotFound:
        raise HTTPException(404, "agent not found")
    record_audit(db, actor=user, action="agent.update", resource_type="agent",
                resource_id=agent_id, outcome="success", request=request,
                metadata={"fields": list(touched.keys())})
    db.commit()
    if schedule_touched:
        # Only reschedule when scheduling actually changed — rescheduling on every
        # unrelated edit (e.g. renaming) would otherwise churn the job unnecessarily.
        from app.scheduler.scheduler import reschedule_agent
        reschedule_agent(agent.id)
    return svc.to_out(agent)


@router.delete("/{agent_id}", response_model=Message)
def delete_agent(agent_id: int, request: Request, db: Session = Depends(get_db),
                 agent: Agent = Depends(require_agent_access("manager")),
                 user: User = Depends(get_current_active_user)):
    svc = _svc(db)
    try:
        svc.archive(agent_id)
    except AgentNotFound:
        raise HTTPException(404, "agent not found")
    record_audit(db, actor=user, action="agent.delete", resource_type="agent",
                resource_id=agent_id, outcome="success", request=request)
    db.commit()
    from app.scheduler.scheduler import unschedule_agent
    unschedule_agent(agent_id)
    return {"detail": "archived"}


@router.post("/{agent_id}/pause", response_model=AgentOut)
def pause_agent(agent_id: int, request: Request, db: Session = Depends(get_db),
                agent: Agent = Depends(require_agent_access("manager")),
                user: User = Depends(get_current_active_user)):
    svc = _svc(db)
    try:
        agent = svc.pause(agent_id)
    except AgentNotFound:
        raise HTTPException(404, "agent not found")
    record_audit(db, actor=user, action="agent.pause", resource_type="agent",
                resource_id=agent_id, outcome="success", request=request)
    db.commit()
    from app.scheduler.scheduler import unschedule_agent
    unschedule_agent(agent_id)
    return svc.to_out(agent)


@router.post("/{agent_id}/resume", response_model=AgentOut)
def resume_agent(agent_id: int, request: Request, db: Session = Depends(get_db),
                 agent: Agent = Depends(require_agent_access("manager")),
                 user: User = Depends(get_current_active_user)):
    svc = _svc(db)
    try:
        agent = svc.resume(agent_id)
    except AgentNotFound:
        raise HTTPException(404, "agent not found")
    record_audit(db, actor=user, action="agent.resume", resource_type="agent",
                resource_id=agent_id, outcome="success", request=request)
    db.commit()
    from app.scheduler.scheduler import reschedule_agent
    reschedule_agent(agent_id)
    return svc.to_out(agent)


@router.post("/{agent_id}/duplicate", response_model=AgentOut, status_code=201)
def duplicate_agent(agent_id: int, request: Request, db: Session = Depends(get_db),
                    agent: Agent = Depends(require_agent_access("viewer")),
                    user: User = Depends(require_role("administrator", "agent_manager"))):
    svc = _svc(db)
    try:
        copy = svc.duplicate(agent_id, owner_id=user.id, workspace_id=user.workspace_id)
    except AgentNotFound:
        raise HTTPException(404, "agent not found")
    record_audit(db, actor=user, action="agent.duplicate", resource_type="agent",
                resource_id=copy.id, outcome="success", request=request,
                metadata={"source_agent_id": agent_id})
    db.commit()
    return svc.to_out(copy)


@router.post("/{agent_id}/run", response_model=RunOut)
def run_agent_now(agent_id: int, request: Request, db: Session = Depends(get_db),
                  agent: Agent = Depends(require_agent_access("researcher")),
                  user: User = Depends(get_current_active_user)):
    record_audit(db, actor=user, action="agent.run_triggered", resource_type="agent",
                resource_id=agent_id, outcome="success", request=request, metadata={"trigger": "manual"})
    db.commit()
    from app.services.run_service import execute_run, run_to_out
    run = execute_run(db, agent, trigger="manual")
    return run_to_out(run)
