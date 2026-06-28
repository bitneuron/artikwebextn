from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _make_due_reminder(client, headers, minutes_ago=5):
    due = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()
    return client.post("/api/reminders", headers=headers, json={
        "title": "Mortgage", "category": "Payment", "priority": "high", "due_at": due,
        "schedule": ["on_due"], "channels": ["email", "in_app"]}).json()


def test_dispatch_creates_notifications_and_bell(auth):
    headers, _, client = auth
    _make_due_reminder(client, headers)
    out = client.post("/api/scheduler/run", headers=headers).json()
    assert out["rules_processed"] == 1
    assert out["notifications_created"] == 2  # in_app + email
    assert out["emails_sent"] == 1

    notifs = client.get("/api/notifications", headers=headers).json()
    assert {n["channel"] for n in notifs} == {"email", "in_app"}
    assert all(n["status"] == "sent" for n in notifs)

    bell = client.get("/api/notifications/bell", headers=headers).json()
    assert bell["unread_count"] == 2
    assert bell["overdue_count"] == 1


def test_dispatch_is_idempotent_dedupe(auth):
    headers, _, client = auth
    _make_due_reminder(client, headers)
    first = client.post("/api/scheduler/run", headers=headers).json()
    second = client.post("/api/scheduler/run", headers=headers).json()
    assert first["notifications_created"] == 2
    assert second["notifications_created"] == 0          # no duplicates
    assert len(client.get("/api/notifications", headers=headers).json()) == 2


def test_mark_read_and_all_and_delete(auth):
    headers, _, client = auth
    _make_due_reminder(client, headers)
    client.post("/api/scheduler/run", headers=headers)
    notifs = client.get("/api/notifications", headers=headers).json()
    nid = notifs[0]["id"]

    assert client.post(f"/api/notifications/{nid}/read", headers=headers).json()["is_read"] is True
    assert client.get("/api/notifications/bell", headers=headers).json()["unread_count"] == 1

    client.post("/api/notifications/read-all", headers=headers)
    assert client.get("/api/notifications/bell", headers=headers).json()["unread_count"] == 0

    assert client.delete(f"/api/notifications/{nid}", headers=headers).status_code == 200
    assert len(client.get("/api/notifications", headers=headers).json()) == 1


def test_respects_channel_preferences(auth):
    headers, _, client = auth
    client.put("/api/preferences", headers=headers, json={"email_notifications": False})
    _make_due_reminder(client, headers)
    out = client.post("/api/scheduler/run", headers=headers).json()
    assert out["emails_sent"] == 0                       # email suppressed by preference
    channels = {n["channel"] for n in client.get("/api/notifications", headers=headers).json()}
    assert channels == {"in_app"}
