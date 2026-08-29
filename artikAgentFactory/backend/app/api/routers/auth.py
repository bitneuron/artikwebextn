from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth.audit import record_audit
from app.auth.deps import get_current_active_user, get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.login_throttle import clear as throttle_clear
from app.core.login_throttle import record_failure as throttle_record_failure
from app.core.login_throttle import seconds_locked
from app.core.password_policy import validate_password
from app.core.security import hash_password, make_session_token, verify_password
from app.models.user import User
from app.schemas.auth import ChangePasswordRequest, LoginRequest
from app.schemas.user import UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "?"


@router.post("/login", response_model=UserOut)
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = _client_ip(request)
    locked = seconds_locked(ip, body.identifier)
    if locked:
        raise HTTPException(429, f"too many attempts — try again in {locked}s")

    user = db.execute(
        select(User).where(or_(User.email == body.identifier, User.username == body.identifier))
    ).scalar_one_or_none()

    # Generic failure message throughout — never reveal whether the account exists.
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        throttle_record_failure(ip, body.identifier)
        record_audit(db, actor=None, action="auth.login_failure", resource_type="auth",
                     resource_id=body.identifier, outcome="failure", request=request)
        db.commit()
        raise HTTPException(401, "invalid credentials")

    throttle_clear(ip, body.identifier)
    user.last_login_at = datetime.now(timezone.utc)
    record_audit(db, actor=user, action="auth.login_success", resource_type="auth",
                 resource_id=user.id, outcome="success", request=request)
    db.commit()
    db.refresh(user)

    token = make_session_token(user.id, user.role, user.password_hash)
    response.set_cookie(
        settings.session_cookie_name, token, httponly=True,
        secure=settings.is_production, samesite="lax", max_age=7 * 24 * 3600,
    )
    return user


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db),
          user: User = Depends(get_current_user)):
    response.delete_cookie(settings.session_cookie_name)
    record_audit(db, actor=user, action="auth.logout", resource_type="auth",
                 resource_id=user.id, outcome="success", request=request)
    db.commit()
    return {"detail": "logged out"}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_active_user)):
    return user


@router.post("/change-password")
def change_password(body: ChangePasswordRequest, request: Request, response: Response,
                    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(401, "current password is incorrect")
    problems = validate_password(body.new_password, email=user.email, username=user.username)
    if problems:
        raise HTTPException(422, "; ".join(problems))
    user.password_hash = hash_password(body.new_password)
    user.must_reset_password = False
    record_audit(db, actor=user, action="auth.password_change", resource_type="auth",
                 resource_id=user.id, outcome="success", request=request)
    db.commit()
    db.refresh(user)
    # The pv-fingerprint trick invalidates every OLD cookie (incl. other devices) the
    # instant password_hash changes — re-mint one for THIS session so the user who
    # just changed their own password isn't immediately logged out too.
    token = make_session_token(user.id, user.role, user.password_hash)
    response.set_cookie(
        settings.session_cookie_name, token, httponly=True,
        secure=settings.is_production, samesite="lax", max_age=7 * 24 * 3600,
    )
    return {"detail": "password changed"}
