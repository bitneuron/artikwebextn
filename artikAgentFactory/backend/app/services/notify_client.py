"""Slack delivery — a direct Incoming Webhook to artikAgentFactory's own dedicated
channel (#artik-agent-notify), separate from the shared #artik-notify channel the
centralized Artik Notifier posts to. Slack Incoming Webhooks are bound to one channel
at creation time, so there's no channel routing to do here — POSTing to the webhook
URL always lands in whichever channel it was created for.

Reads SLACK_WEBHOOK_URL from core/secrets.py (Secrets Manager in prod, env locally).
Ships safely "disabled" until it's configured — never raises, never fabricates
delivery.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request

from app.core.config import settings
from app.core.secrets import get_secret

log = logging.getLogger("notification")


def slack_configured() -> bool:
    return bool(get_secret("SLACK_WEBHOOK_URL"))


def _http_post(url: str, payload: dict, timeout: float) -> tuple[int, str]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace") if e.fp else str(e)


def send_slack_notification(*, event_type: str, severity: str, title: str, message: str,
                            metadata: dict | None = None) -> tuple[bool, str]:
    """Post one event to the artikAgentFactory Slack webhook. `event_type`/`severity`/
    `metadata` are accepted for call-site symmetry with the previous relay-based
    signature but aren't sent — a plain Incoming Webhook only takes text/blocks.
    Returns (ok, detail). Never raises — a notification failure must never affect a
    run's own status (run_service.py already finalizes before this is ever called)."""
    webhook_url = get_secret("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return False, "slack not configured (SLACK_WEBHOOK_URL)"

    text = f"*{title}*\n\n{message}" if title else message
    payload = {"text": text}

    attempts = max(1, settings.notification_retry_count)
    last_err = "unknown"
    for i in range(1, attempts + 1):
        try:
            status, body = _http_post(webhook_url, payload, settings.notification_timeout_seconds)
            if 200 <= status < 300:
                return True, "sent"
            last_err = f"http {status}: {body[:200]}"
        except Exception as e:  # noqa: BLE001 — never propagate
            last_err = str(e)
        log.warning("slack webhook delivery attempt %d/%d failed: %s", i, attempts, last_err)
        if i < attempts:
            time.sleep(min(2 ** (i - 1), 5))  # bounded backoff
    log.error("slack webhook delivery FAILED after %d attempts: %s", attempts, last_err)
    return False, last_err
