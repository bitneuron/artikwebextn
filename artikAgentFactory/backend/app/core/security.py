"""Password hashing + session tokens — same mechanism as artikBroker (ArtikFinance),
reused deliberately rather than reinvented (PBKDF2-HMAC-SHA256, stateless
HMAC-signed cookie carrying a password-hash fingerprint so any password change
instantly invalidates every previously-issued cookie, with zero server-side
session-revocation table needed). See `artikBroker/users_db.py` and `app.py`
(`_make_token`/`_parse_token`/`_pwd_fp`) for the reference implementation.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path

from app.core.config import settings

PBKDF2_ITERS = 200_000
SESSION_SLIDING_SECONDS = 60 * 60          # re-mint the cookie after this long
SESSION_ABSOLUTE_MAX_SECONDS = 7 * 24 * 3600  # never valid beyond this, even if refreshed


def hash_password(pw: str) -> str:
    """pbkdf2_sha256$iters$salt_hex$hash_hex — never store plaintext."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", (pw or "").encode(), salt, PBKDF2_ITERS)
    return f"pbkdf2_sha256${PBKDF2_ITERS}${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    """Constant-time verification against a stored pbkdf2 hash."""
    try:
        algo, iters, salt, h = (stored or "").split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", (pw or "").encode(), bytes.fromhex(salt), int(iters))
        return hmac.compare_digest(dk.hex(), h)
    except Exception:  # noqa: BLE001
        return False


def _resolve_secret() -> str:
    s = os.environ.get("APP_SECRET")
    if s:
        return s
    if settings.is_production:
        raise RuntimeError("APP_SECRET must be set in production (it signs session cookies).")
    # dev: persist a random secret so sessions survive --reload restarts
    p = Path(__file__).resolve().parents[2] / ".dev_secret"
    try:
        if p.exists():
            return p.read_text(encoding="utf-8").strip()
        sec = os.urandom(32).hex()
        p.write_text(sec, encoding="utf-8")
        return sec
    except Exception:  # noqa: BLE001
        return "dev-insecure-secret"


APP_SECRET = _resolve_secret()


def password_fingerprint(password_hash: str) -> str:
    """Fingerprint of a user's CURRENT password hash — embedded in the session so a
    password change/reset instantly voids every previously-issued cookie."""
    return hmac.new(APP_SECRET.encode(), (password_hash or "").encode(), hashlib.sha256).hexdigest()[:16]


def make_session_token(user_id: int, role: str, password_hash: str, *, issued_at: int | None = None) -> str:
    now = int(time.time())
    payload = {
        "uid": user_id, "role": role, "pv": password_fingerprint(password_hash),
        "iat": issued_at if issued_at is not None else now,
        "exp": now + SESSION_SLIDING_SECONDS,
    }
    raw = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig = hmac.new(APP_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def parse_session_token(tok: str) -> dict | None:
    try:
        raw, sig = (tok or "").rsplit(".", 1)
        good = hmac.new(APP_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, good):
            return None
        payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        now = int(time.time())
        if int(payload.get("exp", 0)) <= now:
            return None
        if now - int(payload.get("iat", now)) > SESSION_ABSOLUTE_MAX_SECONDS:
            return None
        return payload
    except Exception:  # noqa: BLE001
        return None
