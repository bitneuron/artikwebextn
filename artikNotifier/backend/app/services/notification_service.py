"""Notification engine: create + deliver notifications through pluggable providers,
manage read/unread, bell counts, and the notification center."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging_config import log_event
from app.core.utils import from_json_list
from app.models.notification import Notification, NotificationHistory
from app.models.reminder import Reminder
from app.models.user import User
from app.notifications.base import DeliveryContext
from app.notifications.registry import get_provider
from app.repositories.notification_repo import NotificationRepository


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class NotificationService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = NotificationRepository(db)

    # ── creation + delivery ───────────────────────────────────────────────────
    def create(self, *, user_id: int, channel: str, title: str, body: str | None,
               reminder_id: int | None = None, rule_id: int | None = None,
               dedupe_key: str | None = None) -> Notification | None:
        if dedupe_key and self.repo.exists_dedupe(dedupe_key):
            return None  # already created for this (reminder, offset, channel)
        n = Notification(user_id=user_id, channel=channel, title=title, body=body,
                         reminder_id=reminder_id, rule_id=rule_id, status="pending",
                         dedupe_key=dedupe_key)
        return self.repo.add(n)

    def deliver(self, n: Notification, *, user: User | None = None, reminder: Reminder | None = None) -> bool:
        provider = get_provider(n.channel)
        if provider is None:
            n.status = "failed"; n.error = f"no provider for channel '{n.channel}'"
            self.db.add(NotificationHistory(notification_id=n.id, channel=n.channel,
                                            status="failed", detail=n.error))
            log_event("notification", "no provider", channel=n.channel, notif_id=n.id)
            return False
        ctx = DeliveryContext(
            to_email=(user.email if user else None),
            user_full_name=(user.full_name if user else None),
            reminder_title=(reminder.title if reminder else n.title),
            reminder_description=(reminder.description if reminder else n.body),
            reminder_notes=(reminder.notes if reminder else None),
            reminder_due_at=(reminder.due_at.isoformat() if reminder and reminder.due_at else None),
            reminder_id=(reminder.id if reminder else n.reminder_id),
        )
        n.attempts += 1
        ok, detail = provider.send(title=n.title, body=n.body, context=ctx)
        n.status = "sent" if ok else "failed"
        n.error = None if ok else detail
        if ok:
            n.sent_at = _utcnow()
        self.db.add(NotificationHistory(notification_id=n.id, channel=n.channel,
                                        status=n.status, detail=detail))
        return ok

    # ── center / bell ─────────────────────────────────────────────────────────
    def to_out(self, n: Notification) -> Notification:
        return n  # pydantic from_attributes handles it

    def list(self, user_id: int, **kw) -> list[Notification]:
        return self.repo.query(user_id, **kw)

    def mark_read(self, user_id: int, notif_id: int) -> Notification | None:
        n = self.repo.get_for_user(notif_id, user_id)
        if not n:
            return None
        n.is_read = True; n.read_at = _utcnow()
        if n.status == "sent":
            n.status = "read"
        self.db.commit(); self.db.refresh(n)
        return n

    def mark_all_read(self, user_id: int) -> int:
        rows = self.repo.query(user_id, unread_only=True, limit=1000)
        for n in rows:
            n.is_read = True; n.read_at = _utcnow()
            if n.status == "sent":
                n.status = "read"
        self.db.commit()
        return len(rows)

    def delete(self, user_id: int, notif_id: int) -> bool:
        n = self.repo.get_for_user(notif_id, user_id)
        if not n:
            return False
        n.status = "deleted"
        self.db.commit()
        return True

    def bell(self, user_id: int) -> dict:
        from app.services.dashboard_service import DashboardService
        ds = DashboardService(self.db)
        due, overdue = ds.due_overdue_counts(user_id)
        return {
            "unread_count": self.repo.unread_count(user_id),
            "due_count": due,
            "overdue_count": overdue,
            "recent": self.repo.query(user_id, limit=10),
        }


def dispatch_due(db: Session, now: datetime | None = None) -> dict:
    """Scheduler tick: fire all due notification rules. Creates an in-app + email
    notification per requested channel (deduped), delivers via providers, retries
    transient failures up to the configured max, records a SchedulerJob, and logs."""
    from app.models.system import SchedulerJob
    from app.repositories.notification_repo import NotificationRuleRepository

    now = now or _utcnow()
    job = SchedulerJob(name="dispatch_due", status="running")
    db.add(job); db.flush()
    svc = NotificationService(db)
    rules_repo = NotificationRuleRepository(db)
    processed = created = emails = errors = 0

    try:
        for rule in rules_repo.due_rules(now):
            processed += 1
            reminder = db.get(Reminder, rule.reminder_id)
            if not reminder or reminder.status in ("completed", "archived", "deleted"):
                rule.fired = True
                continue
            user = db.get(User, rule.user_id)
            prefs = user.preferences if user else None
            for channel in from_json_list(rule.channels):
                # honor user channel preferences
                if channel == "email" and prefs and not prefs.email_notifications:
                    continue
                if channel == "in_app" and prefs and not prefs.in_app_notifications:
                    continue
                dedupe = f"{rule.dedupe_key}:{channel}"
                title = f"Reminder: {reminder.title}"
                body = reminder.description or f"Due {reminder.due_at:%Y-%m-%d %H:%M}"
                n = svc.create(user_id=rule.user_id, channel=channel, title=title, body=body,
                               reminder_id=reminder.id, rule_id=rule.id, dedupe_key=dedupe)
                if n is None:
                    continue  # already delivered (dedupe)
                created += 1
                ok = svc.deliver(n, user=user, reminder=reminder)
                # retry transient failures within the same tick
                tries = 1
                while not ok and tries < settings.notification_max_retries:
                    ok = svc.deliver(n, user=user, reminder=reminder)
                    tries += 1
                if ok and channel == "email":
                    emails += 1
                if not ok:
                    errors += 1
            rule.fired = True
        job.status = "success"
    except Exception as e:  # noqa: BLE001
        job.status = "failed"; job.detail = str(e)[:500]; errors += 1
        log_event("error", "scheduler dispatch failed", error=str(e))
    finally:
        job.rules_processed = processed
        job.notifications_created = created
        job.emails_sent = emails
        job.errors = errors
        job.finished_at = _utcnow()
        db.commit()

    log_event("scheduler", "dispatch complete", processed=processed, created=created,
              emails=emails, errors=errors)
    return {"rules_processed": processed, "notifications_created": created,
            "emails_sent": emails, "errors": errors}
