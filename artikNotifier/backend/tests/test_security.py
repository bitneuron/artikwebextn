"""Security regression tests: auth required, IDOR, RBAC, no plaintext, XSS-safe, safe errors."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.database import SessionLocal
from app.models.user import User


def _reg(client, email, pw="password123"):
    r = client.post("/api/auth/register", json={"email": email, "password": pw, "full_name": "X"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _due(mins=60):
    return (datetime.now(timezone.utc) + timedelta(minutes=mins)).isoformat()


# ── 1. login required ─────────────────────────────────────────────────────────
def test_login_required_everywhere(client):
    for path in ["/api/reminders", "/api/notifications", "/api/dashboard",
                 "/api/preferences", "/api/assistant/history"]:
        assert client.get(path).status_code == 401
    assert client.post("/api/assistant/chat", json={"message": "hi"}).status_code == 401
    assert client.post("/api/reminders", json={"title": "x", "due_at": _due()}).status_code == 401


# ── 2. IDOR: a user cannot reach another user's reminders/notifications ───────
def test_idor_reminders_and_notifications(client):
    a = _reg(client, "alice@x.com")
    b = _reg(client, "bob@x.com")
    rid = client.post("/api/reminders", headers=a, json={"title": "Alice secret", "due_at": _due()}).json()["id"]

    # Bob cannot read / update / delete / act on Alice's reminder
    assert client.get(f"/api/reminders/{rid}", headers=b).status_code == 404
    assert client.put(f"/api/reminders/{rid}", headers=b, json={"title": "hacked"}).status_code == 404
    assert client.delete(f"/api/reminders/{rid}", headers=b).status_code == 404
    assert client.post(f"/api/reminders/{rid}/complete", headers=b).status_code == 404
    # Alice still can
    assert client.get(f"/api/reminders/{rid}", headers=a).status_code == 200
    # Bob's reminder list never contains Alice's items
    assert all("Alice" not in r["title"] for r in client.get("/api/reminders", headers=b).json())

    # notifications: Bob cannot read/delete a notification that isn't his
    assert client.post("/api/notifications/999999/read", headers=b).status_code == 404
    assert client.delete("/api/notifications/999999", headers=b).status_code == 404


# ── 3. RBAC: admin-only endpoints blocked for normal users ───────────────────
def test_rbac_admin_only(client):
    normal = _reg(client, "normal@x.com")           # not in ADMIN_EMAILS → role=user
    admin = _reg(client, "tester@example.com")        # in ADMIN_EMAILS → role=admin

    assert client.get("/api/admin/users", headers=normal).status_code == 403
    assert client.post("/api/scheduler/run", headers=normal).status_code == 403
    assert client.post("/api/admin/users/1/deactivate", headers=normal).status_code == 403

    # admin can
    assert client.get("/api/admin/users", headers=admin).status_code == 200
    assert client.post("/api/scheduler/run", headers=admin).status_code == 200


def test_self_registration_cannot_escalate_role(client):
    # role is ignored on register; a normal email is never admin
    r = client.post("/api/auth/register", json={"email": "evil@x.com", "password": "password123",
                                                "role": "admin", "full_name": "E"})
    assert r.status_code == 201
    assert r.json()["user"]["role"] == "user"


# ── 4. no plaintext password anywhere; never returned by the API ─────────────
def test_password_is_hashed_and_never_exposed(client):
    h = _reg(client, "secure@x.com", pw="SuperSecret123")
    me = client.get("/api/auth/me", headers=h)
    assert "password" not in me.text.lower()       # no password / password_hash in response

    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == "secure@x.com").one()
        assert u.password_hash and u.password_hash != "SuperSecret123"
        assert u.password_hash.startswith("$argon2")   # Argon2 hash, not plaintext
        assert "SuperSecret123" not in u.password_hash
    finally:
        db.close()


# ── 5. XSS payloads are stored/returned as data (React escapes on render) ────
def test_xss_payload_stored_safely(client):
    h = _reg(client, "xss@x.com")
    payload = '<script>alert("xss")</script>'
    r = client.post("/api/reminders", headers=h, json={
        "title": payload, "notes": '<img src=x onerror=alert(1)>', "due_at": _due()})
    assert r.status_code == 201
    got = client.get(f"/api/reminders/{r.json()['id']}", headers=h).json()
    # stored verbatim as data (no HTML execution server-side; the SPA escapes it)
    assert got["title"] == payload
    # the assistant echoes user content but only as plain text in JSON (escaped on render)
    chat = client.post("/api/assistant/chat", headers=h, json={"message": payload}).json()
    assert "reply" in chat


# ── 6. invalid / malicious ids return safe errors, not 500 ───────────────────
def test_invalid_ids_safe_errors(client):
    h = _reg(client, "ids@x.com")
    assert client.get("/api/reminders/999999", headers=h).status_code == 404
    # SQL-injection-style id is a path param typed as int → 422, never executes
    assert client.get("/api/reminders/1%20OR%201=1", headers=h).status_code == 422
    assert client.get("/api/reminders/' OR '1'='1", headers=h).status_code in (404, 422)


# ── 7. security headers present ──────────────────────────────────────────────
def test_security_headers(client):
    r = client.get("/api/health")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert "Content-Security-Policy" in r.headers
