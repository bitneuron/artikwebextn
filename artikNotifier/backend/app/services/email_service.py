"""SMTP email sender with Jinja HTML templates. Falls back to console/log when SMTP
is not configured (dev) so the app is fully runnable without a mail server."""
from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import settings
from app.core.logging_config import log_event

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "email"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


def render(template_name: str, **context) -> str:
    return _env.get_template(template_name).render(brand="Artik Notifier",
                                                   frontend_url=settings.frontend_url, **context)


def send_email(to: str, subject: str, html: str) -> tuple[bool, str]:
    """Returns (ok, detail). Never raises; failures are reported for retry/logging."""
    if not settings.smtp_host:
        if settings.email_console_fallback:
            log_event("notification", "email (console fallback)", to=to, subject=subject)
            return True, "console-fallback"
        return False, "smtp-not-configured"
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.smtp_from
        msg["To"] = to
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_from, [to], msg.as_string())
        log_event("notification", "email sent", to=to, subject=subject)
        return True, "sent"
    except Exception as e:  # noqa: BLE001
        log_event("error", "email send failed", to=to, error=str(e))
        return False, str(e)[:300]
