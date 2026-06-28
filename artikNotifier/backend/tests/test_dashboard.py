from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _r(client, headers, title, minutes):
    due = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()
    return client.post("/api/reminders", headers=headers,
                       json={"title": title, "due_at": due, "schedule": ["on_due"]})


def test_dashboard_counts(auth):
    headers, _, client = auth
    _r(client, headers, "overdue one", -120)
    _r(client, headers, "due soon", 30)
    rid = _r(client, headers, "to complete", 60).json()["id"]
    client.post(f"/api/reminders/{rid}/complete", headers=headers)

    d = client.get("/api/dashboard", headers=headers).json()
    assert d["counts"]["overdue"] >= 1
    assert d["counts"]["completed"] == 1
    assert "upcoming" in d["counts"] and "unread" in d["counts"]
    assert isinstance(d["overdue"], list)


def test_calendar(auth):
    headers, _, client = auth
    now = datetime.now(timezone.utc)
    _r(client, headers, "this month", 60)
    cal = client.get(f"/api/calendar?year={now.year}&month={now.month}", headers=headers).json()
    assert cal["month"] == now.month
    assert len(cal["days"]) >= 28
    assert any(day["reminders"] for day in cal["days"])


def test_health_and_options(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["database"] == "ok"
    o = client.get("/api/options").json()
    assert "critical" in o["priorities"] and "monthly" in o["recurrences"]
    assert "email" in o["channels"] and "in_app" in o["channels"]
