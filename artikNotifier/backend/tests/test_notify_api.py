"""Centralized cross-app notifications API: auth, forwarding, formatting, audit."""
from __future__ import annotations

from app.api.routers.notify_api import build_slack_text
from app.core.database import SessionLocal
from app.models.system import AuditLog
from app.schemas.notify import SlackNotifyIn

PAYLOAD = {
    "source_app": "artikBroker",
    "event_type": "agent_completed",
    "severity": "success",
    "title": "Artik Broker Agent Completed",
    "message": "The Financial Analysis Agent completed successfully.",
    "channel": "#artik-notify",
    "metadata": {
        "agent_name": "Financial Analysis Agent", "agent_id": "agent-123",
        "job_id": "job-456", "task_name": "Analyze AAPL portfolio impact",
        "status": "completed", "duration_seconds": 202, "environment": "production",
        "job_url": "https://broker.example/jobs/job-456",
    },
}


def _capture_slack(monkeypatch):
    sent = {}
    import app.api.routers.notify_api as mod

    def fake_post(text, blocks=None):
        sent["text"] = text
        return True, "delivered"

    monkeypatch.setattr(mod, "post_slack", fake_post)
    return sent


def test_requires_api_key(client):
    assert client.post("/api/v1/notifications/slack", json=PAYLOAD).status_code == 401
    assert client.post("/api/v1/notifications/slack", json=PAYLOAD,
                       headers={"X-API-Key": "wrong"}).status_code == 401


def test_forwards_and_formats(client, monkeypatch):
    sent = _capture_slack(monkeypatch)
    r = client.post("/api/v1/notifications/slack", json=PAYLOAD,
                    headers={"X-API-Key": "test-key-123"})
    assert r.status_code == 200 and r.json()["ok"] is True
    txt = sent["text"]
    assert "✅" in txt and "Artik Broker Agent Completed" in txt
    assert "Financial Analysis Agent" in txt
    assert "Analyze AAPL portfolio impact" in txt
    assert "3m 22s" in txt                     # 202s formatted
    assert "production" in txt and "job-456" in txt
    assert "View Job" in txt


def test_failed_event_shows_error_and_emoji(client, monkeypatch):
    sent = _capture_slack(monkeypatch)
    body = {**PAYLOAD, "severity": "error", "title": "Artik Broker Agent Failed",
            "metadata": {**PAYLOAD["metadata"], "status": "failed",
                         "error_message": "Timeout calling market data provider."}}
    r = client.post("/api/v1/notifications/slack", json=body,
                    headers={"X-API-Key": "test-key-123"})
    assert r.status_code == 200
    assert "❌" in sent["text"] and "Timeout calling market data provider." in sent["text"]


def test_event_is_audited(client, monkeypatch):
    _capture_slack(monkeypatch)
    client.post("/api/v1/notifications/slack", json=PAYLOAD, headers={"X-API-Key": "test-key-123"})
    db = SessionLocal()
    try:
        rows = db.query(AuditLog).filter(AuditLog.action == "notify.slack").all()
        assert rows and "artikBroker" in rows[-1].detail
        assert "test-key-123" not in (rows[-1].detail or "")   # key never logged
    finally:
        db.close()


# ── unit: severity emoji + duration formatting + fallbacks ──────────────────────
def test_severity_emoji_mapping():
    for sev, emoji in [("success", "✅"), ("error", "❌"), ("warning", "⚠️"), ("info", "ℹ️")]:
        txt = build_slack_text(SlackNotifyIn(severity=sev, title="T"))
        assert txt.startswith(emoji)


def test_duration_and_message_fallback():
    # no metadata → message body is used
    txt = build_slack_text(SlackNotifyIn(title="T", message="hello world"))
    assert "hello world" in txt
    # duration formatting hours/minutes/seconds
    from app.api.routers.notify_api import _fmt_duration
    assert _fmt_duration(202) == "3m 22s"
    assert _fmt_duration(45) == "45s"
    assert _fmt_duration(3661) == "1h 1m 1s"
    assert _fmt_duration(None) is None
