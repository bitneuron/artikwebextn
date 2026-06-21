"""SQLite-backed user accounts for artikBroker (replaces the single shared password).

Stdlib only (no new deps). Passwords are PBKDF2-SHA256 hashed (never plaintext),
stored in the same `pbkdf2_sha256$iters$salt$hash` format the old APP_PASSWORD_HASH
used. The DB path is `USERS_DB_PATH` or `<app>/config/users.db`.

This module owns ONLY storage + hashing. Session cookies, the auth middleware and
the HTTP endpoints live in app.py (which holds APP_SECRET).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("USERS_DB_PATH", str(HERE / "config" / "users.db")))

PBKDF2_ITERS = 200_000
ROLES = ("admin", "financial_analyst", "user")

_lock = threading.RLock()


# ── time / hashing ────────────────────────────────────────────────────────────
def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


# ── connection / schema ───────────────────────────────────────────────────────
def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH), timeout=10, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_db() -> None:
    with _lock, _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                username TEXT UNIQUE NOT NULL,
                full_name TEXT,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                is_active INTEGER NOT NULL DEFAULT 1,
                must_reset_password INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_login_at TEXT,
                created_by INTEGER
            )
        """)


# ── row helpers ───────────────────────────────────────────────────────────────
def _row(r: sqlite3.Row | None) -> dict | None:
    if r is None:
        return None
    return dict(r)


def safe(u: dict | None) -> dict | None:
    """Public view of a user — never exposes password_hash."""
    if not u:
        return None
    return {
        "id": u["id"], "email": u["email"], "username": u["username"],
        "full_name": u.get("full_name"), "role": u["role"],
        "is_active": bool(u["is_active"]),
        "must_reset_password": bool(u["must_reset_password"]),
        "created_at": u.get("created_at"), "updated_at": u.get("updated_at"),
        "last_login_at": u.get("last_login_at"), "created_by": u.get("created_by"),
    }


# ── queries ───────────────────────────────────────────────────────────────────
def count_users() -> int:
    with _conn() as c:
        return c.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]


def get_by_id(uid) -> dict | None:
    with _conn() as c:
        return _row(c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())


def get_by_login(login: str) -> dict | None:
    """Look up by email (lowercased) or username (case-insensitive)."""
    key = (login or "").strip()
    with _conn() as c:
        return _row(c.execute(
            "SELECT * FROM users WHERE email=? OR LOWER(username)=LOWER(?) LIMIT 1",
            (key.lower(), key)).fetchone())


def list_users() -> list[dict]:
    with _conn() as c:
        return [safe(dict(r)) for r in
                c.execute("SELECT * FROM users ORDER BY role='admin' DESC, id ASC").fetchall()]


# ── mutations ─────────────────────────────────────────────────────────────────
class UserError(ValueError):
    """Raised for validation problems (duplicate email/username, bad role, …)."""


def _norm_email(e: str) -> str:
    return (e or "").strip().lower()


def create_user(*, email: str, username: str, password: str, full_name: str = "",
                role: str = "user", must_reset_password: bool = True,
                is_active: bool = True, created_by=None) -> dict:
    email = _norm_email(email)
    username = (username or "").strip()
    if not email or "@" not in email:
        raise UserError("a valid email is required")
    if not username:
        raise UserError("username is required")
    if not password:
        raise UserError("a temporary password is required")
    if role not in ROLES:
        raise UserError("role must be 'admin' or 'user'")
    now = _now()
    with _lock, _conn() as c:
        if c.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            raise UserError("a user with that email already exists")
        if c.execute("SELECT 1 FROM users WHERE LOWER(username)=LOWER(?)", (username,)).fetchone():
            raise UserError("a user with that username already exists")
        cur = c.execute(
            """INSERT INTO users (email,username,full_name,password_hash,role,is_active,
                                  must_reset_password,created_at,updated_at,created_by)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (email, username, (full_name or "").strip(), hash_password(password), role,
             1 if is_active else 0, 1 if must_reset_password else 0, now, now, created_by))
        new_id = cur.lastrowid
    return get_by_id(new_id)   # read after the transaction commits


def update_user(uid, *, full_name=None, email=None, username=None, role=None,
                is_active=None, must_reset_password=None) -> dict:
    sets, vals = [], []
    with _lock, _conn() as c:
        existing = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not existing:
            raise UserError("user not found")
        if email is not None:
            email = _norm_email(email)
            if not email or "@" not in email:
                raise UserError("a valid email is required")
            dup = c.execute("SELECT 1 FROM users WHERE email=? AND id<>?", (email, uid)).fetchone()
            if dup:
                raise UserError("a user with that email already exists")
            sets.append("email=?"); vals.append(email)
        if username is not None:
            username = (username or "").strip()
            if not username:
                raise UserError("username is required")
            dup = c.execute("SELECT 1 FROM users WHERE LOWER(username)=LOWER(?) AND id<>?",
                            (username, uid)).fetchone()
            if dup:
                raise UserError("a user with that username already exists")
            sets.append("username=?"); vals.append(username)
        if full_name is not None:
            sets.append("full_name=?"); vals.append((full_name or "").strip())
        if role is not None:
            if role not in ROLES:
                raise UserError("role must be 'admin' or 'user'")
            sets.append("role=?"); vals.append(role)
        if is_active is not None:
            sets.append("is_active=?"); vals.append(1 if is_active else 0)
        if must_reset_password is not None:
            sets.append("must_reset_password=?"); vals.append(1 if must_reset_password else 0)
        if not sets:
            return get_by_id(uid)
        sets.append("updated_at=?"); vals.append(_now())
        vals.append(uid)
        c.execute(f"UPDATE users SET {', '.join(sets)} WHERE id=?", vals)
    return get_by_id(uid)


def set_password(uid, password: str, *, must_reset: bool) -> dict:
    if not password:
        raise UserError("a password is required")
    with _lock, _conn() as c:
        if not c.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone():
            raise UserError("user not found")
        c.execute("UPDATE users SET password_hash=?, must_reset_password=?, updated_at=? WHERE id=?",
                  (hash_password(password), 1 if must_reset else 0, _now(), uid))
    return get_by_id(uid)


def set_active(uid, active: bool) -> dict:
    with _lock, _conn() as c:
        c.execute("UPDATE users SET is_active=?, updated_at=? WHERE id=?",
                  (1 if active else 0, _now(), uid))
    return get_by_id(uid)


def touch_last_login(uid) -> None:
    with _lock, _conn() as c:
        c.execute("UPDATE users SET last_login_at=? WHERE id=?", (_now(), uid))


def delete_user(uid) -> None:
    with _lock, _conn() as c:
        c.execute("DELETE FROM users WHERE id=?", (uid,))


def admin_count(exclude_id=None) -> int:
    with _conn() as c:
        if exclude_id is not None:
            return c.execute("SELECT COUNT(*) AS n FROM users WHERE role='admin' AND is_active=1 AND id<>?",
                             (exclude_id,)).fetchone()["n"]
        return c.execute("SELECT COUNT(*) AS n FROM users WHERE role='admin' AND is_active=1").fetchone()["n"]


# ── bootstrap / migration ─────────────────────────────────────────────────────
def ensure_initial_admin(is_production: bool) -> None:
    """Create the first admin if the table is empty.

    - INITIAL_ADMIN_PASSWORD set → create admin from INITIAL_ADMIN_* (no forced reset).
    - else in production → raise (fail startup with a clear message).
    - else in dev → create a convenience admin (admin / admin) and warn loudly.
    Never overwrites/recreates once any user exists.
    """
    init_db()
    if count_users() > 0:
        return
    pw = os.environ.get("INITIAL_ADMIN_PASSWORD")
    if pw:
        email = _norm_email(os.environ.get("INITIAL_ADMIN_EMAIL", "admin@artikbroker.local"))
        username = (os.environ.get("INITIAL_ADMIN_USERNAME", "admin") or "admin").strip()
        create_user(email=email, username=username, password=pw, full_name="Administrator",
                    role="admin", must_reset_password=False)
        print(f"[users] created initial admin '{username}' <{email}> from INITIAL_ADMIN_* env.", flush=True)
        return
    if is_production:
        raise RuntimeError(
            "No users exist and INITIAL_ADMIN_PASSWORD is not set. Refusing to start in "
            "production. Set INITIAL_ADMIN_EMAIL / INITIAL_ADMIN_USERNAME / INITIAL_ADMIN_PASSWORD.")
    # dev convenience admin
    create_user(email="admin@local", username="admin", password="admin", full_name="Dev Admin",
                role="admin", must_reset_password=False)
    print("[users] ⚠ DEV: no INITIAL_ADMIN_PASSWORD — created dev admin admin/admin. "
          "Set INITIAL_ADMIN_PASSWORD (and ENVIRONMENT=production) before deploying.", flush=True)
