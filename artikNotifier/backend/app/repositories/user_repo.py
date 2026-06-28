from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.core.utils import ensure_aware
from app.models.user import PasswordReset, Session as DbSession, User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email.lower().strip())
        return self.db.execute(stmt).scalar_one_or_none()


class SessionRepository(BaseRepository[DbSession]):
    model = DbSession

    def get_by_token(self, refresh_token: str) -> DbSession | None:
        stmt = select(DbSession).where(DbSession.refresh_token == refresh_token)
        return self.db.execute(stmt).scalar_one_or_none()

    def revoke_all_for_user(self, user_id: int) -> None:
        for s in self.list(user_id=user_id):
            s.revoked = True
        self.db.flush()


class PasswordResetRepository(BaseRepository[PasswordReset]):
    model = PasswordReset

    def get_valid(self, token: str) -> PasswordReset | None:
        stmt = select(PasswordReset).where(PasswordReset.token == token)
        pr = self.db.execute(stmt).scalar_one_or_none()
        if not pr or pr.used or ensure_aware(pr.expires_at) < datetime.now(timezone.utc):
            return None
        return pr
