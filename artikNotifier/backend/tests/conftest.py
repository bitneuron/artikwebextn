"""Pytest fixtures: isolated SQLite DB per test + an authenticated client."""
from __future__ import annotations

import os
import tempfile

import pytest

# Configure the app for testing BEFORE importing it.
_TMP_DB = os.path.join(tempfile.gettempdir(), "artik_notifier_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["ENVIRONMENT"] = "development"
os.environ["EMAIL_CONSOLE_FALLBACK"] = "true"
# The default fixture user is an admin (so dispatch tests can trigger the scheduler).
# RBAC tests register their own separate NORMAL users to verify 403s.
os.environ["ADMIN_EMAILS"] = "tester@example.com"
os.environ["RATE_LIMIT_PER_MINUTE"] = "100000"   # don't throttle the test suite
os.environ["NOTIFY_API_KEYS"] = "test-key-123"   # centralized notifications API auth

from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def auth(client):
    """Register a user and return (headers, tokens, client)."""
    r = client.post("/api/auth/register", json={
        "email": "tester@example.com", "password": "password123", "full_name": "Tester"})
    assert r.status_code == 201, r.text
    body = r.json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    return headers, body, client
