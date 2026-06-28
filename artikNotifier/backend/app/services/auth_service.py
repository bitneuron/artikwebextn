"""Authentication: register/login/refresh/logout, password change + reset.
Passwords hashed with Argon2; refresh sessions persisted for revocation."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging_config import log_event
from app.core.security import (create_access_token, create_refresh_token, decode_token,
                               generate_reset_token, hash_password, verify_password)
from app.core.utils import ensure_aware
from app.models.user import PasswordReset, Session as DbSession, User, UserPreferences
from app.repositories.user_repo import (PasswordResetRepository, SessionRepository, UserRepository)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuthError(Exception):
    def __init__(self, detail: str, status: int = 400):
        self.detail = detail
        self.status = status


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.users = UserRepository(db)
        self.sessions = SessionRepository(db)
        self.resets = PasswordResetRepository(db)

    def register(self, *, email: str, password: str, full_name: str | None, timezone_: str) -> User:
        email = email.lower().strip()
        if self.users.get_by_email(email):
            raise AuthError("an account with that email already exists", 409)
        user = User(email=email, full_name=full_name, password_hash=hash_password(password),
                    timezone=timezone_ or "UTC")
        self.users.add(user)
        self.db.add(UserPreferences(user_id=user.id))
        # seed default categories for the user
        from app.models.enums import DEFAULT_CATEGORIES
        from app.models.reminder import Category
        for name in DEFAULT_CATEGORIES:
            self.db.add(Category(user_id=user.id, name=name, is_default=True))
        self.db.commit(); self.db.refresh(user)
        log_event("audit", "user registered", user_id=user.id, email=email)
        return user

    def _issue_tokens(self, user: User, *, user_agent: str | None, ip: str | None) -> dict:
        access = create_access_token(user.id, user.role)
        refresh = create_refresh_token(user.id)
        self.db.add(DbSession(
            user_id=user.id, refresh_token=refresh, user_agent=user_agent, ip_address=ip,
            expires_at=_utcnow() + timedelta(days=settings.refresh_token_expire_days)))
        user.last_login_at = _utcnow()
        self.db.commit()
        return {"access_token": access, "refresh_token": refresh, "user": user}

    def login(self, *, email: str, password: str, user_agent=None, ip=None) -> dict:
        user = self.users.get_by_email(email.lower().strip())
        if not user or not user.is_active or not verify_password(password, user.password_hash):
            log_event("security", "failed login", email=email, ip=ip)
            raise AuthError("invalid email or password", 401)
        return self._issue_tokens(user, user_agent=user_agent, ip=ip)

    def refresh(self, refresh_token: str, *, user_agent=None, ip=None) -> dict:
        payload = decode_token(refresh_token, "refresh")
        sess = self.sessions.get_by_token(refresh_token)
        if not payload or not sess or sess.revoked or ensure_aware(sess.expires_at) < _utcnow():
            raise AuthError("invalid or expired refresh token", 401)
        user = self.users.get(int(payload["sub"]))
        if not user or not user.is_active:
            raise AuthError("account inactive", 401)
        sess.revoked = True  # rotate
        return self._issue_tokens(user, user_agent=user_agent, ip=ip)

    def logout(self, refresh_token: str | None) -> None:
        if not refresh_token:
            return
        sess = self.sessions.get_by_token(refresh_token)
        if sess:
            sess.revoked = True
            self.db.commit()

    def change_password(self, user: User, current: str, new: str) -> None:
        if not verify_password(current, user.password_hash):
            raise AuthError("current password is incorrect", 400)
        user.password_hash = hash_password(new)
        self.sessions.revoke_all_for_user(user.id)  # invalidate other sessions
        self.db.commit()
        log_event("audit", "password changed", user_id=user.id)

    def forgot_password(self, email: str) -> str | None:
        """Always succeeds to the caller (no user enumeration). Returns the token
        for dev/testing (in prod it's emailed, not returned)."""
        user = self.users.get_by_email(email.lower().strip())
        if not user:
            return None
        token = generate_reset_token()
        self.db.add(PasswordReset(
            user_id=user.id, token=token,
            expires_at=_utcnow() + timedelta(minutes=settings.password_reset_expire_minutes)))
        self.db.commit()
        # send reset email (console fallback in dev)
        from app.services.email_service import render, send_email
        link = f"{settings.frontend_url}/reset-password?token={token}"
        html = render("reset.html", name=user.full_name or "there", link=link)
        send_email(user.email, "Reset your Artik Notifier password", html)
        log_event("audit", "password reset requested", user_id=user.id)
        return token

    def reset_password(self, token: str, new_password: str) -> None:
        pr = self.resets.get_valid(token)
        if not pr:
            raise AuthError("invalid or expired reset token", 400)
        user = self.users.get(pr.user_id)
        if not user:
            raise AuthError("account not found", 404)
        user.password_hash = hash_password(new_password)
        pr.used = True
        self.sessions.revoke_all_for_user(user.id)
        self.db.commit()
        log_event("audit", "password reset completed", user_id=user.id)
