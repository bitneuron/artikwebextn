"""Gmail SMTP delivery for "action" agents (see templates/definitions/email_scheduler.py)
— sends as one fixed, server-configured Gmail account using an App Password (requires
2-Step Verification on that account: myaccount.google.com/apppasswords). Reads
GMAIL_SMTP_USER / GMAIL_SMTP_APP_PASSWORD via core/secrets.py (Secrets Manager in
prod, env locally) — same resolution path as notify_client.py's SLACK_WEBHOOK_URL.
Ships safely "disabled" until configured; never raises."""
from __future__ import annotations

import logging
import re
import smtplib
import time
from email.mime.text import MIMEText

from app.core.config import settings
from app.core.secrets import get_secret

log = logging.getLogger("notification")

_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 465


def gmail_configured() -> bool:
    return bool(get_secret("GMAIL_SMTP_USER")) and bool(get_secret("GMAIL_SMTP_APP_PASSWORD"))


def _parse_recipients(raw: str) -> list[str]:
    """The "to" field accepts multiple addresses separated by comma OR semicolon (the
    latter being how Outlook/most mail clients present a multi-recipient field) —
    smtplib needs each as a separate envelope recipient, not one literal string."""
    return [p.strip() for p in re.split(r"[;,]", raw) if p.strip()]


def send_email(*, to_email: str, subject: str, body: str) -> tuple[bool, str]:
    """Returns (ok, detail). Never raises — a delivery failure must only ever surface
    as a failed AgentRun, exactly like a research-agent pipeline error."""
    user = get_secret("GMAIL_SMTP_USER")
    app_password = get_secret("GMAIL_SMTP_APP_PASSWORD")
    if not user or not app_password:
        return False, "gmail not configured (GMAIL_SMTP_USER / GMAIL_SMTP_APP_PASSWORD)"

    recipients = _parse_recipients(to_email)
    if not recipients:
        return False, "no valid recipient address"

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = ", ".join(recipients)

    attempts = max(1, settings.notification_retry_count)
    last_err = "unknown"
    for i in range(1, attempts + 1):
        try:
            with smtplib.SMTP_SSL(_SMTP_HOST, _SMTP_PORT, timeout=settings.notification_timeout_seconds) as smtp:
                smtp.login(user, app_password)
                smtp.sendmail(user, recipients, msg.as_string())
            return True, "sent"
        except Exception as e:  # noqa: BLE001 — never propagate
            last_err = str(e)
        log.warning("gmail smtp delivery attempt %d/%d failed: %s", i, attempts, last_err)
        if i < attempts:
            time.sleep(min(2 ** (i - 1), 5))  # bounded backoff
    log.error("gmail smtp delivery FAILED after %d attempts: %s", attempts, last_err)
    return False, last_err
