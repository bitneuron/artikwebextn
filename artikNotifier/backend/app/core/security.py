"""Password hashing (Argon2) + JWT access/refresh tokens + opaque reset tokens.

Never stores or logs plaintext passwords. Constant-time verification via passlib.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

ALGORITHM = "HS256"


# ── passwords ─────────────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return pwd_context.verify(password, password_hash)
    except Exception:  # noqa: BLE001 — malformed hash etc.
        return False


# ── JWT tokens ────────────────────────────────────────────────────────────────
def _create_token(subject: str, token_type: str, expires_delta: timedelta,
                  extra: dict | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "jti": secrets.token_urlsafe(8),
        **(extra or {}),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_access_token(user_id: int, role: str = "user") -> str:
    return _create_token(str(user_id), "access",
                         timedelta(minutes=settings.access_token_expire_minutes),
                         {"role": role})


def create_refresh_token(user_id: int) -> str:
    return _create_token(str(user_id), "refresh",
                         timedelta(days=settings.refresh_token_expire_days))


def decode_token(token: str, expected_type: str | None = None) -> dict | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if expected_type and payload.get("type") != expected_type:
        return None
    return payload


# ── opaque tokens (password reset) ───────────────────────────────────────────
def generate_reset_token() -> str:
    return secrets.token_urlsafe(32)
