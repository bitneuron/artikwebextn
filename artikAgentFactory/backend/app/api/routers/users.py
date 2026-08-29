from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.audit import record_audit
from app.auth.deps import require_role
from app.core.database import get_db
from app.core.password_policy import validate_password
from app.core.security import hash_password
from app.models.user import User
from app.schemas.common import Message
from app.schemas.user import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/api/users", tags=["users"])
_ADMIN = Depends(require_role("administrator"))


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: object = _ADMIN):
    return list(db.execute(select(User).order_by(User.created_at)).scalars().all())


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, request: Request, db: Session = Depends(get_db), actor: User = _ADMIN):
    if db.execute(select(User).where((User.email == body.email) | (User.username == body.username))).first():
        raise HTTPException(409, "a user with that email or username already exists")
    problems = validate_password(body.password, email=body.email, username=body.username)
    if problems:
        raise HTTPException(422, "; ".join(problems))
    if body.role not in ("administrator", "agent_manager", "researcher", "viewer"):
        raise HTTPException(422, "invalid role")
    user = User(
        email=body.email, username=body.username, full_name=body.full_name,
        password_hash=hash_password(body.password), role=body.role,
        workspace_id=actor.workspace_id, created_by=actor.id, must_reset_password=True,
    )
    db.add(user)
    db.flush()
    record_audit(db, actor=actor, action="user.create", resource_type="user",
                 resource_id=user.id, outcome="success", request=request,
                 metadata={"role": user.role})
    db.commit()
    db.refresh(user)
    return user


@router.put("/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, request: Request,
                db: Session = Depends(get_db), actor: User = _ADMIN):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "user not found")
    fields = body.model_dump(exclude_unset=True)
    role_changed = "role" in fields and fields["role"] != target.role
    if "full_name" in fields:
        target.full_name = fields["full_name"]
    if "role" in fields and fields["role"] is not None:
        if fields["role"] not in ("administrator", "agent_manager", "researcher", "viewer"):
            raise HTTPException(422, "invalid role")
        target.role = fields["role"]
    if "is_active" in fields and fields["is_active"] is not None:
        target.is_active = fields["is_active"]
    if role_changed:
        record_audit(db, actor=actor, action="user.role_change", resource_type="user",
                     resource_id=target.id, outcome="success", request=request,
                     metadata={"new_role": target.role})
    if "is_active" in fields and fields["is_active"] is False:
        record_audit(db, actor=actor, action="user.deactivate", resource_type="user",
                     resource_id=target.id, outcome="success", request=request)
    db.commit()
    db.refresh(target)
    return target


@router.post("/{user_id}/force-reset", response_model=Message)
def force_password_reset(user_id: int, request: Request, db: Session = Depends(get_db), actor: User = _ADMIN):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "user not found")
    target.must_reset_password = True
    record_audit(db, actor=actor, action="user.force_password_reset", resource_type="user",
                 resource_id=target.id, outcome="success", request=request)
    db.commit()
    return {"detail": "password reset required on next login"}
