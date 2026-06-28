"""Admin-only endpoints (RBAC). Every action is audit-logged. Admins manage users
but reminder/notification *content* stays private to its owner (not exposed here)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.database import get_db
from app.core.logging_config import log_event
from app.models.system import AuditLog
from app.models.user import User
from app.schemas.auth import UserOut

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _audit(db: Session, actor: User, action: str, entity_id: int | None, detail: str) -> None:
    db.add(AuditLog(user_id=actor.id, action=action, entity="user",
                    entity_id=entity_id, detail=detail))
    db.commit()
    log_event("audit", action, actor=actor.id, entity_id=entity_id, detail=detail)


@router.get("/users", response_model=list[UserOut])
def list_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.execute(select(User).order_by(User.id)).scalars().all()
    _audit(db, admin, "admin.list_users", None, f"{len(rows)} users")
    return rows  # UserOut never includes password_hash


@router.post("/users/{user_id}/role", response_model=UserOut)
def set_role(user_id: int, role: str, admin: User = Depends(require_admin),
             db: Session = Depends(get_db)):
    if role not in ("admin", "user"):
        raise HTTPException(400, "role must be 'admin' or 'user'")
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "user not found")
    # don't allow removing the last admin
    if target.role == "admin" and role == "user":
        admins = db.execute(select(User).where(User.role == "admin")).scalars().all()
        if len(admins) <= 1:
            raise HTTPException(400, "cannot demote the last admin")
    target.role = role
    db.commit(); db.refresh(target)
    _audit(db, admin, "admin.set_role", user_id, f"role={role}")
    return target


@router.post("/users/{user_id}/deactivate", response_model=UserOut)
def deactivate(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "user not found")
    if target.id == admin.id:
        raise HTTPException(400, "you cannot deactivate yourself")
    target.is_active = False
    db.commit(); db.refresh(target)
    _audit(db, admin, "admin.deactivate", user_id, "deactivated")
    return target
