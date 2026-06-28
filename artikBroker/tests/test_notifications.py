"""Tests for the Artik Broker → Artik Notifier notification client + lifecycle hook."""
from __future__ import annotations

import pytest

from notifications import (AgentEvent, NotifyClient, NotifyConfig, build_payload,
                           normalize_status, notify_agent_terminal, severity_for)
from notifications import client as client_mod


def cfg(**kw) -> NotifyConfig:
    base = dict(enabled=True, api_url="https://notify.example", api_key="secret-k",
                app_name="artikBroker", base_url="https://broker.example",
                timeout=5.0, retries=3, environment="test", version="1.0.0")
    base.update(kw)
    return NotifyConfig(**base)


def make_transport(results):
    """Fake _http_post: yields each (status, body) per attempt; raises if an item is an Exception."""
    state = {"n": 0, "payloads": [], "url": None, "headers": None}
    seq = list(results)

    def _t(url, headers, payload, timeout):
        state["n"] += 1
        state["payloads"].append(payload)
        state["url"], state["headers"] = url, headers
        item = seq[min(state["n"] - 1, len(seq) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    return _t, state


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(client_mod.time, "sleep", lambda *_: None)  # fast retries


# ── severity mapping + payload formatting ───────────────────────────────────────
def test_severity_mapping():
    assert severity_for("completed") == "success"
    assert severity_for("failed") == "error"
    assert severity_for("cancelled") == "warning"
    assert severity_for("timeout") == "error"
    assert severity_for("skipped") == "info"
    assert severity_for("anything-else") == "info"


@pytest.mark.parametrize("status,sev", [
    ("completed", "success"), ("failed", "error"), ("cancelled", "warning"),
    ("timeout", "error"), ("skipped", "info"),
])
def test_payload_for_each_terminal_state(status, sev):
    ev = AgentEvent(agent_name="Risk Analysis Agent", status=status, job_id="job-1",
                    task_name="Generate risk summary",
                    started_at="2026-06-28T10:00:00Z", completed_at="2026-06-28T10:03:22Z")
    p = build_payload(ev, "artikBroker")
    assert p["severity"] == sev
    assert p["event_type"] == f"agent_{status}"
    assert p["source_app"] == "artikBroker" and p["channel"] == "#artik-notify"
    md = p["metadata"]
    assert md["status"] == status and md["agent_name"] == "Risk Analysis Agent"
    assert md["duration_seconds"] == 202.0          # computed from timestamps


def test_normalize_status_aliases():
    assert normalize_status("success") == "completed"
    assert normalize_status("partial") == "completed"
    assert normalize_status("error") == "failed"
    assert normalize_status("canceled") == "cancelled"
    assert normalize_status("timed_out") == "timeout"
    assert normalize_status(None) == "completed"


# ── delivery: success / failure / retries ───────────────────────────────────────
def test_api_success(monkeypatch):
    t, st = make_transport([(200, "ok")])
    monkeypatch.setattr(client_mod, "_http_post", t)
    assert NotifyClient(cfg()).notify(AgentEvent(agent_name="A", status="completed", job_id="j1")) is True
    assert st["n"] == 1
    assert st["headers"]["X-API-Key"] == "secret-k"
    assert st["url"].endswith("/api/v1/notifications/slack")


def test_api_failure_after_retries(monkeypatch):
    t, st = make_transport([(500, "boom")])
    monkeypatch.setattr(client_mod, "_http_post", t)
    assert NotifyClient(cfg(retries=3)).notify(AgentEvent(agent_name="A", status="failed")) is False
    assert st["n"] == 3                              # retried the configured number of times


def test_retry_then_success(monkeypatch):
    t, st = make_transport([(503, "later"), (200, "ok")])
    monkeypatch.setattr(client_mod, "_http_post", t)
    assert NotifyClient(cfg(retries=3)).notify(AgentEvent(agent_name="A", status="completed")) is True
    assert st["n"] == 2


def test_network_error_is_swallowed(monkeypatch):
    t, st = make_transport([RuntimeError("connection refused")])
    monkeypatch.setattr(client_mod, "_http_post", t)
    # returns False, never raises
    assert NotifyClient(cfg(retries=2)).notify(AgentEvent(agent_name="A", status="failed")) is False
    assert st["n"] == 2


# ── config guards: disabled / missing url / missing key ─────────────────────────
def test_disabled_skips_without_calling(monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(client_mod, "_http_post",
                        lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1), (200, "ok"))[1])
    assert NotifyClient(cfg(enabled=False)).notify(AgentEvent(agent_name="A", status="completed")) is False
    assert calls["n"] == 0


def test_missing_url_or_key_skips(monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(client_mod, "_http_post",
                        lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1), (200, "ok"))[1])
    assert NotifyClient(cfg(api_url="")).notify(AgentEvent(agent_name="A", status="completed")) is False
    assert NotifyClient(cfg(api_key="")).notify(AgentEvent(agent_name="A", status="completed")) is False
    assert calls["n"] == 0


# ── enrichment + future/new agents are generic ──────────────────────────────────
def test_job_url_and_env_enriched_for_any_agent(monkeypatch):
    t, st = make_transport([(200, "ok")])
    monkeypatch.setattr(client_mod, "_http_post", t)
    ok = NotifyClient(cfg()).notify(AgentEvent(agent_name="Brand New Agent 9000",
                                               status="completed", job_id="job-9"))
    assert ok is True
    md = st["payloads"][0]["metadata"]
    assert md["agent_name"] == "Brand New Agent 9000"          # no per-agent code needed
    assert md["job_url"] == "https://broker.example/jobs/job-9"
    assert md["environment"] == "test" and md["version"] == "1.0.0"


# ── the lifecycle entry point never breaks the caller ───────────────────────────
def test_notify_agent_terminal_never_raises(monkeypatch):
    monkeypatch.setattr(client_mod, "_http_post",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setenv("NOTIFICATIONS_ENABLED", "true")
    monkeypatch.setenv("ARTIK_NOTIFY_API_URL", "https://notify.example")
    monkeypatch.setenv("ARTIK_NOTIFY_API_KEY", "k")
    monkeypatch.setenv("NOTIFICATION_RETRY_COUNT", "1")
    client_mod._default_client = None               # rebuild from env
    # must return False, not raise — a notification failure can't break an agent
    assert notify_agent_terminal(agent_name="Any Future Agent", status="completed", job_id="j") is False
    client_mod._default_client = None


def test_notify_agent_terminal_success(monkeypatch):
    t, st = make_transport([(200, "ok")])
    monkeypatch.setattr(client_mod, "_http_post", t)
    monkeypatch.setenv("NOTIFICATIONS_ENABLED", "true")
    monkeypatch.setenv("ARTIK_NOTIFY_API_URL", "https://notify.example")
    monkeypatch.setenv("ARTIK_NOTIFY_API_KEY", "k")
    client_mod._default_client = None
    ok = notify_agent_terminal(agent_name="Valuation Agent", status="completed",
                               job_id="job-77", task_name="DCF for AAPL",
                               started_at="2026-06-28T10:00:00Z",
                               completed_at="2026-06-28T10:01:00Z")
    assert ok is True
    md = st["payloads"][0]["metadata"]
    assert md["agent_name"] == "Valuation Agent" and md["duration_seconds"] == 60.0
    client_mod._default_client = None
