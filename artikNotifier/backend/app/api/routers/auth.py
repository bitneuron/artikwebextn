from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.schemas.auth import (ChangePasswordIn, ForgotPasswordIn, LoginIn, RefreshIn,
                              RegisterIn, ResetPasswordIn, TokenOut, UserOut)
from app.schemas.dashboard import Message
from app.services.auth_service import AuthError, AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _svc(db: Session) -> AuthService:
    return AuthService(db)


def _meta(req: Request) -> dict:
    return {"user_agent": req.headers.get("user-agent"), "ip": req.client.host if req.client else None}


@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    svc = _svc(db)
    try:
        svc.register(email=body.email, password=body.password,
                     full_name=body.full_name, timezone_=body.timezone)
        return svc.login(email=body.email, password=body.password, **_meta(request))
    except AuthError as e:
        raise HTTPException(e.status, e.detail)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    try:
        return _svc(db).login(email=body.email, password=body.password, **_meta(request))
    except AuthError as e:
        raise HTTPException(e.status, e.detail)


@router.post("/refresh", response_model=TokenOut)
def refresh(body: RefreshIn, request: Request, db: Session = Depends(get_db)):
    try:
        return _svc(db).refresh(body.refresh_token, **_meta(request))
    except AuthError as e:
        raise HTTPException(e.status, e.detail)


@router.post("/logout", response_model=Message)
def logout(body: RefreshIn | None = None, db: Session = Depends(get_db)):
    _svc(db).logout(body.refresh_token if body else None)
    return {"detail": "logged out"}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/change-password", response_model=Message)
def change_password(body: ChangePasswordIn, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    try:
        _svc(db).change_password(user, body.current_password, body.new_password)
        return {"detail": "password updated"}
    except AuthError as e:
        raise HTTPException(e.status, e.detail)


@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordIn, db: Session = Depends(get_db)):
    token = _svc(db).forgot_password(body.email)
    resp = {"detail": "if that account exists, a reset link has been sent"}
    if not settings.is_production and token:   # dev convenience only
        resp["dev_token"] = token
    return resp


@router.post("/reset-password", response_model=Message)
def reset_password(body: ResetPasswordIn, db: Session = Depends(get_db)):
    try:
        _svc(db).reset_password(body.token, body.new_password)
        return {"detail": "password reset"}
    except AuthError as e:
        raise HTTPException(e.status, e.detail)
