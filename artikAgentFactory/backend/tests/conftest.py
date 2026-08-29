"""Env vars must be set BEFORE any `app.*` module is imported (pydantic-settings reads
them once, at import time), so this happens at conftest module level — pytest imports
conftest.py before collecting test files."""
from __future__ import annotations

import os
import tempfile

_fd, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["NOTIFICATIONS_ENABLED"] = "false"
os.environ["APP_SECRET"] = "test-secret-not-for-production"
# Deterministic bootstrap admin so tests don't have to scrape a randomly-generated
# dev password out of stdout.
os.environ["INITIAL_ADMIN_EMAIL"] = "admin@test.local"
os.environ["INITIAL_ADMIN_PASSWORD"] = "bootstrap-admin-pass-9000"

import pytest
from fastapi.testclient import TestClient

from app.core.database import Base, SessionLocal, engine, init_db
from app.core.password_policy import validate_password
from app.core.security import hash_password
from app.main import app
from app.models.user import User
from app.models.workspace import Workspace


@pytest.fixture(scope="session", autouse=True)
def _init_test_db():
    init_db()
    yield
    os.remove(_DB_PATH)


@pytest.fixture()
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client():
    with TestClient(app) as c:
        # ensure_initial_admin() now always sets must_reset_password=True (production
        # security requirement) — tests need a pre-cleared bootstrap admin so login_as()
        # can hit protected endpoints immediately without a separate reset step.
        db = SessionLocal()
        try:
            admin = db.query(User).filter(User.email == "admin@test.local").first()
            if admin and admin.must_reset_password:
                admin.must_reset_password = False
                db.commit()
        finally:
            db.close()
        yield c


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """The security middleware's limiter state is module-level (persists across the
    whole pytest session) — clear it before every test so one test's request volume
    can't spuriously 429 the next test."""
    from app.core.security_middleware import _general_hits, _login_hits
    _general_hits.clear()
    _login_hits.clear()
    yield


@pytest.fixture(autouse=True)
def _reset_login_throttle():
    from app.core.login_throttle import _LOGIN_FAILS
    _LOGIN_FAILS.clear()
    yield


@pytest.fixture(autouse=True)
def _clean_tables():
    """Every test starts from an empty DB — cheap since these are small local tables.
    ensure_initial_admin() (called by the app's lifespan, i.e. on every `client`
    fixture use) re-bootstraps the deterministic admin@test.local account afterward."""
    yield
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


ADMIN_EMAIL = "admin@test.local"
ADMIN_PASSWORD = "bootstrap-admin-pass-9000"

_ROLE_PASSWORDS = {
    "administrator": ADMIN_PASSWORD,
    "agent_manager": "manager-strong-pass-7001",
    "researcher": "research-strong-pass-7002",
    "viewer": "viewer-strong-pass-7003",
}


def login_as(client: TestClient, role: str) -> dict:
    """Logs `client` in as a user with the given role, creating the user first if it
    doesn't already exist (administrator always exists via bootstrap). Returns the
    logged-in user dict. The TestClient's cookiejar carries the session for
    subsequent calls on the same `client` instance."""
    password = _ROLE_PASSWORDS[role]
    if role == "administrator":
        resp = client.post("/api/auth/login", json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert resp.status_code == 200, resp.text
        return resp.json()

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == f"{role}@test.local").first()
        if not existing:
            ws = db.query(Workspace).filter(Workspace.slug == "default").first()
            assert validate_password(password) == []
            db.add(User(
                email=f"{role}@test.local", username=role, full_name=role.title(),
                password_hash=hash_password(password), role=role, workspace_id=ws.id,
                is_active=True, must_reset_password=False,
            ))
            db.commit()
    finally:
        db.close()

    resp = client.post("/api/auth/login", json={"identifier": f"{role}@test.local", "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()
