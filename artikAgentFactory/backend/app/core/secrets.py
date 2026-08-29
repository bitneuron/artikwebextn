"""Secret resolution: AWS Secrets Manager in prod/staging, plain env vars locally.
Exact paths: `{secrets_prefix}/{name}` e.g. `artikagentfactory/SLACK_WEBHOOK_URL`
(this app's own Slack Incoming Webhook — see services/notify_client.py). Never logs
a fetched value; caches successful lookups briefly to avoid hammering Secrets Manager
on every notification."""
from __future__ import annotations

import os
import time

from app.core.config import settings

_CACHE: dict[str, tuple[float, str | None]] = {}
_CACHE_TTL_SECONDS = 300


def get_secret(name: str) -> str | None:
    if settings.secrets_backend != "aws":
        return os.environ.get(name) or None

    now = time.monotonic()
    cached = _CACHE.get(name)
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    value = _fetch_from_secrets_manager(f"{settings.secrets_prefix}/{name}")
    _CACHE[name] = (now, value)
    return value


def _fetch_from_secrets_manager(secret_id: str) -> str | None:
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:  # noqa: BLE001
        return None
    try:
        client = boto3.client("secretsmanager")
        resp = client.get_secret_value(SecretId=secret_id)
        return resp.get("SecretString")
    except ClientError:
        return None
    except Exception:  # noqa: BLE001 — never let secret resolution crash a run
        return None
