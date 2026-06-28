"""Artik Broker → Artik Notifier notification client.

Routes agent lifecycle events to the centralized Artik Notifier API (which forwards to
Slack #artik-notify). Reads all config from environment variables, retries with backoff,
times out, logs every attempt (never the API key), and NEVER raises into the caller — a
notification failure must not break an agent's execution.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from dataclasses import dataclass

from .events import build_payload, normalize_status
from .schemas import AgentEvent

log = logging.getLogger("artikbroker.notifications")

_SLACK_PATH = "/api/v1/notifications/slack"


def _http_post(url: str, headers: dict, payload: dict, timeout: float) -> tuple[int, str]:
    """POST JSON via stdlib (no extra deps). Returns (status_code, body)."""
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={**headers, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:  # 4xx/5xx still carry a status
        return e.code, e.read().decode("utf-8", "replace") if e.fp else str(e)


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class NotifyConfig:
    enabled: bool
    api_url: str
    api_key: str
    app_name: str
    base_url: str
    timeout: float
    retries: int
    environment: str
    version: str

    @classmethod
    def from_env(cls) -> "NotifyConfig":
        return cls(
            enabled=_env_bool("NOTIFICATIONS_ENABLED", True),
            api_url=(os.getenv("ARTIK_NOTIFY_API_URL") or "").strip(),
            api_key=(os.getenv("ARTIK_NOTIFY_API_KEY") or "").strip(),
            app_name=os.getenv("ARTIK_BROKER_APP_NAME", "artikBroker"),
            base_url=(os.getenv("ARTIK_BROKER_BASE_URL") or "").strip(),
            timeout=float(os.getenv("NOTIFICATION_TIMEOUT_SECONDS", "10")),
            retries=int(os.getenv("NOTIFICATION_RETRY_COUNT", "3")),
            environment=os.getenv("ENVIRONMENT", "development"),
            version=os.getenv("ARTIK_BROKER_VERSION", "1.0.0"),
        )


class NotifyClient:
    def __init__(self, config: NotifyConfig | None = None):
        self.cfg = config or NotifyConfig.from_env()

    def notify(self, event: AgentEvent) -> bool:
        """Send one agent event. Returns True on delivery, False otherwise. Never raises."""
        cfg = self.cfg
        if not cfg.enabled:
            log.info("notifications disabled — skip (agent=%s status=%s)",
                     event.agent_name, event.status)
            return False
        if not cfg.api_url or not cfg.api_key:
            log.warning("notify skipped: missing ARTIK_NOTIFY_API_URL / ARTIK_NOTIFY_API_KEY "
                        "(agent=%s job=%s)", event.agent_name, event.job_id)
            return False

        # Enrich from config when the caller didn't supply these.
        if not event.job_url and cfg.base_url and event.job_id:
            event.job_url = f"{cfg.base_url.rstrip('/')}/jobs/{event.job_id}"
        event.environment = event.environment or cfg.environment
        event.version = event.version or cfg.version

        payload = build_payload(event, cfg.app_name)
        url = cfg.api_url.rstrip("/") + _SLACK_PATH
        headers = {"X-API-Key": cfg.api_key}        # key in header, never logged

        attempts = max(1, cfg.retries)
        last_err = None
        for i in range(1, attempts + 1):
            try:
                status, body = _http_post(url, headers, payload, cfg.timeout)
                if 200 <= status < 300:
                    log.info("notify ok agent=%s job=%s status=%s attempt=%d/%d",
                             event.agent_name, event.job_id, event.status, i, attempts)
                    return True
                last_err = f"http {status}: {body[:120]}"
            except Exception as e:  # noqa: BLE001 — never propagate
                last_err = str(e)
            log.warning("notify attempt %d/%d failed agent=%s job=%s err=%s",
                        i, attempts, event.agent_name, event.job_id, last_err)
            if i < attempts:
                time.sleep(min(2 ** (i - 1), 5))    # bounded backoff
        log.error("notify FAILED after %d attempts agent=%s job=%s status=%s err=%s",
                  attempts, event.agent_name, event.job_id, event.status, last_err)
        return False


_default_client: NotifyClient | None = None


def get_client() -> NotifyClient:
    global _default_client
    if _default_client is None:
        _default_client = NotifyClient()
    return _default_client


def notify_agent_terminal(*, agent_name: str, status: str, agent_id: str | None = None,
                          job_id: str | None = None, task_name: str | None = None,
                          started_at: str | None = None, completed_at: str | None = None,
                          duration_seconds: float | None = None,
                          error_message: str | None = None, job_url: str | None = None) -> bool:
    """Build an AgentEvent and send it through the default client.

    Safe to call from any agent/worker — it never raises, so a notification problem can
    never break agent execution. This is the single entry point the lifecycle hook uses,
    so every current and future agent is covered without custom code.
    """
    try:
        event = AgentEvent(
            agent_name=agent_name, status=normalize_status(status), agent_id=agent_id,
            job_id=job_id, task_name=task_name, started_at=started_at,
            completed_at=completed_at, duration_seconds=duration_seconds,
            error_message=error_message, job_url=job_url)
        return get_client().notify(event)
    except Exception:  # noqa: BLE001 — defensive: lifecycle hook must never crash a worker
        log.exception("notify_agent_terminal crashed (suppressed)")
        return False
