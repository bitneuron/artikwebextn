"""Notification provider plugin interface.

Every delivery channel (email, in-app, and future SMS/Push/Slack/Webhook/…) implements
this same interface, so new channels plug in by registering a provider — the core
scheduler/notification engine never changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class DeliveryContext:
    to_email: str | None = None
    user_full_name: str | None = None
    reminder_title: str | None = None
    reminder_description: str | None = None
    reminder_notes: str | None = None
    reminder_due_at: str | None = None
    reminder_id: int | None = None


class NotificationProvider(ABC):
    channel: str  # must match a Channel enum value

    @abstractmethod
    def send(self, *, title: str, body: str | None, context: DeliveryContext) -> tuple[bool, str]:
        """Deliver one notification. Returns (ok, detail). Must never raise."""
        raise NotImplementedError
