"""Verifies the outbound request to the Slack Incoming Webhook: POST to
SLACK_WEBHOOK_URL with a {"text": ...} payload, no other params (Incoming Webhooks
are bound to one channel at creation time — no routing to do on our side)."""
import json

from app.core.config import settings
from app.services import notify_client


def test_slack_configured_requires_webhook_url(monkeypatch):
    monkeypatch.setattr(notify_client, "get_secret", lambda name: None)
    assert notify_client.slack_configured() is False

    monkeypatch.setattr(notify_client, "get_secret", lambda name: "https://hooks.slack.com/services/x")
    assert notify_client.slack_configured() is True


def test_send_slack_notification_posts_to_the_webhook(monkeypatch):
    monkeypatch.setattr(notify_client, "get_secret",
                        lambda name: "https://hooks.slack.com/services/xyz" if name == "SLACK_WEBHOOK_URL" else None)

    captured = {}

    def fake_post(url, payload, timeout):
        captured["url"] = url
        captured["payload"] = payload
        return 200, "ok"

    monkeypatch.setattr(notify_client, "_http_post", fake_post)

    ok, detail = notify_client.send_slack_notification(
        event_type="agent_run_completed", severity="success",
        title="Agent X — Success", message="body text", metadata={"agent_id": 1})

    assert ok is True
    assert captured["url"] == "https://hooks.slack.com/services/xyz"
    assert captured["payload"] == {"text": "*Agent X — Success*\n\nbody text"}


def test_send_slack_notification_retries_then_fails_cleanly(monkeypatch):
    monkeypatch.setattr(notify_client, "get_secret", lambda name: "https://hooks.slack.com/services/xyz")
    monkeypatch.setattr(settings, "notification_retry_count", 2)
    monkeypatch.setattr(notify_client.time, "sleep", lambda *_: None)

    attempts = {"n": 0}

    def failing_post(url, payload, timeout):
        attempts["n"] += 1
        return 500, "internal error"

    monkeypatch.setattr(notify_client, "_http_post", failing_post)

    ok, detail = notify_client.send_slack_notification(
        event_type="agent_run_completed", severity="error", title="t", message="m")

    assert ok is False
    assert attempts["n"] == 2
    assert "http 500" in detail
