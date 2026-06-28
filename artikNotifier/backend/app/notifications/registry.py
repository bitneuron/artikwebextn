"""Provider registry — the plugin seam. Future channels register here without touching
the notification engine. Unregistered channels degrade gracefully (skipped + logged)."""
from __future__ import annotations

from app.notifications.base import NotificationProvider
from app.notifications.providers import EmailProvider, InAppProvider, SlackProvider

_REGISTRY: dict[str, NotificationProvider] = {}


def register(provider: NotificationProvider) -> None:
    _REGISTRY[provider.channel] = provider


def get_provider(channel: str) -> NotificationProvider | None:
    return _REGISTRY.get(channel)


def available_channels() -> list[str]:
    return sorted(_REGISTRY.keys())


# Built-in channels (Slack degrades to console-fallback until SLACK_WEBHOOK_URL is set).
register(InAppProvider())
register(EmailProvider())
register(SlackProvider())
