"""Slack notification provider: registration, console-fallback, webhook POST, errors."""
from __future__ import annotations

from app.notifications.base import DeliveryContext
from app.notifications.providers import SlackProvider
from app.notifications.registry import available_channels, get_provider


def test_slack_is_registered_channel(client):
    assert "slack" in available_channels()
    assert isinstance(get_provider("slack"), SlackProvider)


def test_slack_options_exposed(auth):
    headers, _, client = auth
    opts = client.get("/api/options").json()
    assert "slack" in opts["all_channels"]
    assert "slack" in opts["channels"]            # now registered → available


def test_slack_console_fallback_when_unset(monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.settings, "slack_webhook_url", "", raising=False)
    ok, detail = SlackProvider().send(title="Hi", body="Body", context=DeliveryContext())
    assert ok and detail == "console-fallback"


def test_slack_posts_to_webhook(monkeypatch):
    from app.core import config
    from app.notifications import providers

    monkeypatch.setattr(config.settings, "slack_webhook_url",
                        "https://hooks.slack.com/services/T/B/X", raising=False)
    captured = {}

    class _Resp:
        status_code = 200
        text = "ok"

    def fake_post(url, json, timeout):       # noqa: A002
        captured["url"] = url
        captured["text"] = json["text"]
        return _Resp()

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    ctx = DeliveryContext(reminder_due_at="2026-07-15T09:00:00+00:00")
    ok, detail = SlackProvider().send(title="Pay tax", body="Property tax", context=ctx)
    assert ok and detail == "delivered"
    assert captured["url"].startswith("https://hooks.slack.com/")
    assert "Pay tax" in captured["text"] and "Property tax" in captured["text"]
    assert "2026-07-15" in captured["text"]


def test_slack_reports_http_error(monkeypatch):
    from app.core import config
    from app.notifications import providers

    monkeypatch.setattr(config.settings, "slack_webhook_url",
                        "https://hooks.slack.com/services/T/B/X", raising=False)

    class _Resp:
        status_code = 404
        text = "no_service"

    monkeypatch.setattr(providers.httpx, "post", lambda *a, **k: _Resp())
    ok, detail = SlackProvider().send(title="x", body=None, context=DeliveryContext())
    assert not ok and "404" in detail


def test_slack_never_raises_on_network_error(monkeypatch):
    from app.core import config
    from app.notifications import providers

    monkeypatch.setattr(config.settings, "slack_webhook_url",
                        "https://hooks.slack.com/services/T/B/X", raising=False)

    def boom(*a, **k):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(providers.httpx, "post", boom)
    ok, detail = SlackProvider().send(title="x", body=None, context=DeliveryContext())
    assert not ok and "error" in detail.lower()
