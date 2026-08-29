from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.audit import record_audit
from app.auth.deps import get_current_active_user, require_owner_or_admin
from app.core.database import get_db
from app.models.agent import Agent
from app.models.agent_access import AgentAccess
from app.models.user import User
from app.schemas.agent_access import AgentAccessIn

router = APIRouter(tags=["agent-access"])

_LEVELS = ("viewer", "researcher", "manager")


def _out(grant: AgentAccess, email: str) -> dict:
    return {
        "id": grant.id, "agent_id": grant.agent_id, "user_id": grant.user_id, "user_email": email,
        "access_level": grant.access_level, "granted_by": grant.granted_by, "created_at": grant.created_at,
    }


@router.get("/api/agents/{agent_id}/access")
def list_access(agent_id: int, db: Session = Depends(get_db), agent: Agent = Depends(require_owner_or_admin)):
    rows = db.execute(
        select(AgentAccess, User.email).join(User, User.id == AgentAccess.user_id)
        .where(AgentAccess.agent_id == agent_id)
    ).all()
    return [_out(grant, email) for grant, email in rows]


@router.post("/api/agents/{agent_id}/access", status_code=201)
def grant_access(agent_id: int, body: AgentAccessIn, request: Request, db: Session = Depends(get_db),
                 agent: Agent = Depends(require_owner_or_admin), actor: User = Depends(get_current_active_user)):
    if body.access_level not in _LEVELS:
        raise HTTPException(422, "invalid access_level")
    target_user = db.get(User, body.user_id)
    if not target_user:
        raise HTTPException(404, "user not found")
    existing = db.execute(
        select(AgentAccess).where(AgentAccess.agent_id == agent_id, AgentAccess.user_id == body.user_id)
    ).scalar_one_or_none()
    if existing:
        existing.access_level = body.access_level
        grant = existing
    else:
        grant = AgentAccess(agent_id=agent_id, user_id=body.user_id,
                            access_level=body.access_level, granted_by=actor.id)
        db.add(grant)
    db.flush()
    record_audit(db, actor=actor, action="agent.access_grant", resource_type="agent",
                resource_id=agent_id, outcome="success", request=request,
                metadata={"user_id": body.user_id, "access_level": body.access_level})
    db.commit()
    db.refresh(grant)
    return _out(grant, target_user.email)


@router.delete("/api/agents/{agent_id}/access/{user_id}")
def revoke_access(agent_id: int, user_id: int, request: Request, db: Session = Depends(get_db),
                  agent: Agent = Depends(require_owner_or_admin), actor: User = Depends(get_current_active_user)):
    grant = db.execute(
        select(AgentAccess).where(AgentAccess.agent_id == agent_id, AgentAccess.user_id == user_id)
    ).scalar_one_or_none()
    if not grant:
        raise HTTPException(404, "grant not found")
    db.delete(grant)
    record_audit(db, actor=actor, action="agent.access_revoke", resource_type="agent",
                resource_id=agent_id, outcome="success", request=request, metadata={"user_id": user_id})
    db.commit()
    return {"detail": "access revoked"}
