"""Artik Assistant chatbot tests — insights, NL answers, history, and isolation."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _due(mins):
    return (datetime.now(timezone.utc) + timedelta(minutes=mins)).isoformat()


def _seed(client, headers):
    # a finance reminder due this week (same-day-only, recurring), an overdue one, no-notes ones
    client.post("/api/reminders", headers=headers, json={
        "title": "Mortgage", "category": "Payment", "due_at": _due(2 * 24 * 60),
        "recurrence": "monthly", "schedule": ["on_due"], "channels": ["email", "in_app"]})
    client.post("/api/reminders", headers=headers, json={
        "title": "Overdue taxes", "category": "Tax", "due_at": _due(-120), "schedule": ["on_due"]})
    for i in range(3):
        client.post("/api/reminders", headers=headers, json={
            "title": f"Personal {i}", "category": "Personal", "due_at": _due(60 + i)})


def test_insights(auth):
    headers, _, client = auth
    _seed(client, headers)
    ins = client.get("/api/assistant/insights", headers=headers).json()
    text = " ".join(ins)
    assert any("finance" in i.lower() for i in ins)            # finance due this week
    assert any("same day" in i.lower() or "on the same day" in i.lower() for i in ins)
    assert any("note" in i.lower() for i in ins)               # reminders without notes
    assert isinstance(ins, list) and len(ins) >= 1


def test_chat_nl_questions(auth):
    headers, _, client = auth
    _seed(client, headers)
    def ask(q): return client.post("/api/assistant/chat", headers=headers, json={"message": q}).json()["reply"]

    assert "week" in ask("What reminders are coming this week?").lower()
    assert "overdue" in ask("Do I have any overdue payments?").lower()
    assert "unread" in ask("Which notifications are unread?").lower()
    assert "suggest" in ask("How should I improve my reminder settings?").lower() \
        or "consider" in ask("How should I improve my reminder settings?").lower()
    assert "Tax" in ask("Show me Tax related reminders") or "tax" in ask("Show me Tax related reminders").lower()
    assert "month" in ask("Summarize my calendar for this month").lower()


def test_chat_history_persisted_and_scoped(auth, client):
    headers, _, _ = auth
    client.post("/api/assistant/chat", headers=headers, json={"message": "hello"})
    hist = client.get("/api/assistant/history", headers=headers).json()
    assert len(hist) == 2 and hist[0]["role"] == "user" and hist[1]["role"] == "assistant"

    # a second user has a separate, empty history (no cross-user leakage)
    other = client.post("/api/auth/register", json={"email": "other@x.com", "password": "password123"}).json()
    oh = {"Authorization": f"Bearer {other['access_token']}"}
    assert client.get("/api/assistant/history", headers=oh).json() == []

    # clear works
    client.delete("/api/assistant/history", headers=headers)
    assert client.get("/api/assistant/history", headers=headers).json() == []


def test_assistant_only_sees_own_data(client):
    a = client.post("/api/auth/register", json={"email": "a2@x.com", "password": "password123"}).json()
    b = client.post("/api/auth/register", json={"email": "b2@x.com", "password": "password123"}).json()
    ah = {"Authorization": f"Bearer {a['access_token']}"}
    bh = {"Authorization": f"Bearer {b['access_token']}"}
    client.post("/api/reminders", headers=ah, json={"title": "Alice-only secret", "category": "Finance",
                                                    "due_at": _due(60)})
    # Bob's assistant must never mention Alice's reminder
    reply = client.post("/api/assistant/chat", headers=bh, json={"message": "show finance reminders"}).json()["reply"]
    assert "Alice-only secret" not in reply
    assert "no active Finance" in reply or "no finance" in reply.lower()
