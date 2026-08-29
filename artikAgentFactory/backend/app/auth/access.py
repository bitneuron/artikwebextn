"""The single IDOR-prevention chokepoint. Every router resolves per-agent access
through `check_access`/`effective_level` rather than hand-rolling ownership checks —
see the approved plan §1 for the resolution rule this implements."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent import Agent
from app.models.agent_access import AgentAccess
from app.models.user import User

LEVELS = {"viewer": 1, "researcher": 2, "manager": 3}


def effective_level(db: Session, user: User, agent: Agent) -> int:
    if user.role == "administrator":
        return LEVELS["manager"]
    if agent.owner_id == user.id:
        return LEVELS["manager"]
    grant = db.execute(
        select(AgentAccess).where(AgentAccess.agent_id == agent.id, AgentAccess.user_id == user.id)
    ).scalar_one_or_none()
    explicit = LEVELS.get(grant.access_level, 0) if grant else 0
    baseline = LEVELS["viewer"] if (agent.visibility == "shared" and agent.workspace_id == user.workspace_id) else 0
    return max(explicit, baseline)


def check_access(db: Session, user: User, agent: Agent, required_level: str) -> bool:
    return effective_level(db, user, agent) >= LEVELS[required_level]


def accessible_agent_ids_subquery(db: Session, user: User):
    """A SQL subquery of agent ids the user can at least view — used to scope list/
    dashboard/aggregate queries server-side (never a Python post-filter of an
    unbounded query, which would still leak row counts/existence via timing/paging)."""
    if user.role == "administrator":
        return select(Agent.id)
    return select(Agent.id).where(
        (Agent.owner_id == user.id)
        | (Agent.id.in_(select(AgentAccess.agent_id).where(AgentAccess.user_id == user.id)))
        | ((Agent.visibility == "shared") & (Agent.workspace_id == user.workspace_id))
    )
