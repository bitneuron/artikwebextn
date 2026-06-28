from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _due(minutes_from_now: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)).isoformat()


def _create(client, headers, **over):
    payload = {"title": "Insurance renewal", "category": "Insurance", "priority": "high",
               "due_at": _due(60), "schedule": ["on_due", "1_day"],
               "channels": ["email", "in_app"], "tags": ["car"]}
    payload.update(over)
    return client.post("/api/reminders", headers=headers, json=payload)


def test_crud_and_tags(auth):
    headers, _, client = auth
    r = _create(client, headers)
    assert r.status_code == 201
    rid = r.json()["id"]
    assert r.json()["tags"] == ["car"] and r.json()["schedule"] == ["on_due", "1_day"]

    assert client.get(f"/api/reminders/{rid}", headers=headers).status_code == 200
    upd = client.put(f"/api/reminders/{rid}", headers=headers,
                     json={"title": "Renewed", "priority": "critical", "tags": ["car", "urgent"]})
    assert upd.status_code == 200 and upd.json()["title"] == "Renewed"
    assert set(upd.json()["tags"]) == {"car", "urgent"}

    assert client.delete(f"/api/reminders/{rid}", headers=headers).status_code == 200
    assert client.get(f"/api/reminders/{rid}", headers=headers).status_code == 404


def test_filter_search_sort(auth):
    headers, _, client = auth
    _create(client, headers, title="Pay taxes", category="Tax", priority="critical")
    _create(client, headers, title="Gym membership", category="Subscription", priority="low")
    assert len(client.get("/api/reminders", headers=headers).json()) == 2
    assert len(client.get("/api/reminders?category=Tax", headers=headers).json()) == 1
    assert len(client.get("/api/reminders?priority=low", headers=headers).json()) == 1
    found = client.get("/api/reminders?search=gym", headers=headers).json()
    assert len(found) == 1 and found[0]["title"] == "Gym membership"


def test_complete_archive_restore_snooze_duplicate(auth):
    headers, _, client = auth
    rid = _create(client, headers).json()["id"]

    assert client.post(f"/api/reminders/{rid}/snooze", headers=headers,
                       json={"minutes": 30}).json()["status"] == "snoozed"
    assert client.post(f"/api/reminders/{rid}/complete", headers=headers).json()["status"] == "completed"
    assert client.post(f"/api/reminders/{rid}/restore", headers=headers).json()["status"] == "active"
    assert client.post(f"/api/reminders/{rid}/archive", headers=headers).json()["status"] == "archived"

    dup = client.post(f"/api/reminders/{rid}/duplicate", headers=headers)
    assert dup.status_code == 200 and dup.json()["id"] != rid
    assert dup.json()["title"].endswith("(copy)")


def test_recurring_complete_rolls_forward(auth):
    headers, _, client = auth
    r = _create(client, headers, recurrence="monthly", due_at=_due(-1))
    rid = r.json()["id"]
    original_due = r.json()["due_at"]
    done = client.post(f"/api/reminders/{rid}/complete", headers=headers).json()
    # recurring → stays active and due date moves forward
    assert done["status"] == "active"
    assert done["due_at"] > original_due
