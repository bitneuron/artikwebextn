"""Built-in providers: in-app, email, and Slack. Add new channels here (or via register())."""
from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.logging_config import log_event
from app.notifications.base import DeliveryContext, NotificationProvider
from app.services.email_service import render, send_email


class InAppProvider(NotificationProvider):
    channel = "in_app"

    def send(self, *, title, body, context: DeliveryContext) -> tuple[bool, str]:
        # In-app notifications are delivered simply by persisting the row (done by the
        # notification engine). Nothing external to call → always "delivered".
        return True, "stored"


class EmailProvider(NotificationProvider):
    channel = "email"

    def send(self, *, title, body, context: DeliveryContext) -> tuple[bool, str]:
        if not context.to_email:
            return False, "no recipient email"
        html = render(
            "reminder.html",
            title=title,
            name=context.user_full_name or "there",
            description=context.reminder_description or body or "",
            notes=context.reminder_notes or "",
            due_at=context.reminder_due_at or "",
            reminder_id=context.reminder_id,
        )
        return send_email(context.to_email, title, html)


class SlackProvider(NotificationProvider):
    """Delivers notifications to a Slack channel via an Incoming Webhook.

    Configured by SLACK_WEBHOOK_URL. When unset, it degrades gracefully to a
    console/log fallback (like email) so the channel is still selectable in dev.
    Never raises — returns (ok, detail) so the engine can record + retry.
    """
    channel = "slack"

    def _format(self, title: str, body: str | None, context: DeliveryContext) -> str:
        lines = [f":bell: *{title}*"]
        detail = body or context.reminder_description or context.reminder_notes
        if detail:
            lines.append(detail)
        if context.reminder_due_at:
            lines.append(f"_Due: {context.reminder_due_at}_")
        return "\n".join(lines)

    def send(self, *, title, body, context: DeliveryContext) -> tuple[bool, str]:
        text = self._format(title, body, context)
        url = settings.slack_webhook_url
        if not url:
            log_event("notification", "slack (console fallback)", title=title)
            return True, "console-fallback"
        try:
            resp = httpx.post(url, json={"text": text}, timeout=10)
            if resp.status_code == 200:
                return True, "delivered"
            return False, f"slack http {resp.status_code}: {resp.text[:120]}"
        except Exception as exc:  # noqa: BLE001 — must never raise into the engine
            return False, f"slack error: {exc}"
