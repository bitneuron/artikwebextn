"""FastAPI auth/authz dependencies. This is the ONLY place session cookies are
read/minted and the ONLY place per-resource access is resolved — every router
depends on these rather than re-implementing checks."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.auth.access import check_access
from app.auth.audit import record_audit
from app.core.config import settings
from app.core.database import get_db
from app.core.security import make_session_token, parse_session_token, password_fingerprint
from app.models.agent import Agent
from app.models.note import Note
from app.models.result import Result
from app.models.run import AgentRun
from app.models.user import User

# Endpoints reachable even while must_reset_password is set, so a user can actually
# clear that flag and isn't locked out of their own account.
_RESET_EXEMPT_PATHS = {"/api/auth/me", "/api/auth/change-password", "/api/auth/logout"}


def get_current_user(request: Request, response: Response, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(settings.session_cookie_name, "")
    payload = parse_session_token(token)
    if not payload:
        raise HTTPException(401, "not authenticated")
    user = db.get(User, payload.get("uid"))
    if not user or not user.is_active:
        raise HTTPException(401, "not authenticated")
    if payload.get("pv") != password_fingerprint(user.password_hash):
        raise HTTPException(401, "session invalidated")  # password changed since this cookie was issued

    # Sliding refresh: re-mint on every authenticated request, preserving the
    # original issue time so the absolute 7-day cap counts from real login, not
    # from the most recent click. Skipped on /logout so it can't fight the cookie
    # deletion the logout endpoint is about to perform on the same Response object.
    if request.url.path != "/api/auth/logout":
        fresh = make_session_token(user.id, user.role, user.password_hash, issued_at=payload.get("iat"))
        response.set_cookie(
            settings.session_cookie_name, fresh, httponly=True,
            secure=settings.is_production, samesite="lax", max_age=7 * 24 * 3600,
        )
    return user


def get_current_active_user(request: Request, user: User = Depends(get_current_user)) -> User:
    if user.must_reset_password and request.url.path not in _RESET_EXEMPT_PATHS:
        raise HTTPException(403, "password reset required")
    return user


def require_role(*roles: str):
    def _dep(request: Request, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)) -> User:
        if user.role not in roles:
            record_audit(db, actor=user, action="access.denied", resource_type="platform",
                         resource_id=request.url.path, outcome="denied", request=request,
                         metadata={"required_roles": list(roles)})
            db.commit()
            raise HTTPException(403, "insufficient permission")
        return user
    return _dep


def require_agent_access(min_level: str):
    def _dep(agent_id: int, request: Request, user: User = Depends(get_current_active_user),
             db: Session = Depends(get_db)) -> Agent:
        agent = db.get(Agent, agent_id)
        if agent is None or agent.status == "archived" or not check_access(db, user, agent, "viewer"):
            raise HTTPException(404, "agent not found")
        if not check_access(db, user, agent, min_level):
            record_audit(db, actor=user, action="access.denied", resource_type="agent",
                         resource_id=agent_id, outcome="denied", request=request,
                         metadata={"required_level": min_level})
            db.commit()
            raise HTTPException(403, "insufficient permission")
        return agent
    return _dep


def require_owner_or_admin(agent_id: int, request: Request, user: User = Depends(get_current_active_user),
                           db: Session = Depends(get_db)) -> Agent:
    agent = db.get(Agent, agent_id)
    if agent is None or agent.status == "archived" or not check_access(db, user, agent, "viewer"):
        raise HTTPException(404, "agent not found")
    if user.role != "administrator" and agent.owner_id != user.id:
        record_audit(db, actor=user, action="access.denied", resource_type="agent",
                     resource_id=agent_id, outcome="denied", request=request,
                     metadata={"required": "owner_or_admin"})
        db.commit()
        raise HTTPException(403, "only the agent owner or an administrator may manage access")
    return agent


def get_result_or_404(min_level: str):
    def _dep(result_id: int, request: Request, user: User = Depends(get_current_active_user),
             db: Session = Depends(get_db)) -> Result:
        result = db.get(Result, result_id)
        if result is None:
            raise HTTPException(404, "result not found")
        agent = db.get(Agent, result.agent_id)
        if agent is None or not check_access(db, user, agent, "viewer"):
            raise HTTPException(404, "result not found")
        if not check_access(db, user, agent, min_level):
            record_audit(db, actor=user, action="access.denied", resource_type="result",
                         resource_id=result_id, outcome="denied", request=request,
                         metadata={"required_level": min_level})
            db.commit()
            raise HTTPException(403, "insufficient permission")
        return result
    return _dep


def get_run_or_404(min_level: str):
    def _dep(run_id: int, request: Request, user: User = Depends(get_current_active_user),
             db: Session = Depends(get_db)) -> AgentRun:
        run = db.get(AgentRun, run_id)
        if run is None:
            raise HTTPException(404, "run not found")
        agent = db.get(Agent, run.agent_id)
        if agent is None or not check_access(db, user, agent, "viewer"):
            raise HTTPException(404, "run not found")
        if not check_access(db, user, agent, min_level):
            raise HTTPException(403, "insufficient permission")
        return run
    return _dep


def get_note_or_404(min_level: str):
    def _dep(note_id: int, request: Request, user: User = Depends(get_current_active_user),
             db: Session = Depends(get_db)) -> Note:
        note = db.get(Note, note_id)
        if note is None:
            raise HTTPException(404, "note not found")
        result = db.get(Result, note.result_id)
        agent = db.get(Agent, result.agent_id) if result else None
        if agent is None or not check_access(db, user, agent, "viewer"):
            raise HTTPException(404, "note not found")
        if not check_access(db, user, agent, min_level):
            raise HTTPException(403, "insufficient permission")
        return note
    return _dep
