"""Built-in providers: in-app and email. Add new channels here (or via register())."""
from __future__ import annotations

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
