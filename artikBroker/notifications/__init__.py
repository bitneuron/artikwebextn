"""Artik Broker notification client.

Routes agent completion/failure events to the centralized Artik Notifier API
(POST /api/v1/notifications/slack), which forwards them to Slack #artik-notify.

The single entry point is `notify_agent_terminal(...)`, called from the generic agent
lifecycle hook in `agent_runner` — so every agent (current and future) is covered with
no per-agent code. All config comes from environment variables; failures are logged and
never propagate into agent execution.
"""
from .client import (NotifyClient, NotifyConfig, get_client, notify_agent_terminal,
                     notify_slack_message)
from .events import (SEVERITY, TERMINAL_STATES, build_payload, normalize_status,
                     severity_for)
from .schemas import AgentEvent

__all__ = [
    "AgentEvent", "NotifyClient", "NotifyConfig", "get_client", "notify_agent_terminal",
    "notify_slack_message",
    "build_payload", "normalize_status", "severity_for", "SEVERITY", "TERMINAL_STATES",
]
