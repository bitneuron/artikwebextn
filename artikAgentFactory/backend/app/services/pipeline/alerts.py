"""Stage 7 (evaluation) + a separate post-finalize delivery stage. Evaluation creates
AlertEvent rows synchronously inside execute_run(), exactly as before. Actual Slack
DELIVERY happens only after the run has reached a terminal state and been committed
(run_service.py calls deliver_alert_events() after finalize) — never mid-run — with
per-(agent,run,type) idempotency and a workspace-level settings gate layered on top
of each agent's own AlertRule.channel."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings as app_settings
from app.core.utils import from_json, to_json
from app.models.agent import Agent
from app.models.alert import AlertEvent, AlertRule
from app.models.notification_delivery import NotificationDelivery
from app.models.notification_settings import NotificationSettings
from app.models.result import Result
from app.models.run import AgentRun
from app.services.notify_client import send_slack_notification, slack_configured
from app.services.pipeline.dates import parse_date
from app.services.pipeline.slack_sanitize import sanitize_for_slack
from app.templates.spec import TemplateSpec

_DEADLINE_KEYS = ("deadline", "application_deadline", "expiration", "scholarship_deadline")

_RULE_TO_SETTING = {
    "run_completed": "notify_on_run_completed",
    "new_results": "notify_on_new_results",
    "changed_results": "notify_on_changed_results",
    "high_priority_match": "notify_on_high_priority",
    "deadline_approaching": "notify_on_deadline_approaching",
    "run_error": "notify_on_run_error",
}

# Run status -> Artik Notifier severity vocabulary (success | error | warning | info),
# mirrored from artikBroker/notifications/events.py's SEVERITY map.
_RUN_STATUS_SEVERITY = {"completed": "success", "partial": "success", "failed": "error", "cancelled": "warning"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _emit(db: Session, agent: Agent, run: AgentRun, rule: AlertRule, result_id: int | None,
          severity: str, title: str, message: str) -> AlertEvent:
    """Creates the AlertEvent row only — delivery is a separate, later stage."""
    event = AlertEvent(agent_id=agent.id, run_id=run.id, rule_id=rule.id, result_id=result_id,
                       severity=severity, title=title, message=message, delivered=False)
    db.add(event)
    db.flush()
    return event


def run_alert_rules(db: Session, agent: Agent, run: AgentRun, results: list[Result]) -> list[AlertEvent]:
    events: list[AlertEvent] = []
    rules = [r for r in agent.alert_rules if r.is_enabled]

    for rule in rules:
        cfg = from_json(rule.config_json, {})

        if rule.rule_type == "run_completed":
            if run.status in ("completed", "partial"):
                total = len(results)
                events.append(_emit(db, agent, run, rule, None, "info",
                    f"Run finished — {total} result(s)",
                    f"{agent.name} completed a run: {run.result_count_new} new, "
                    f"{run.result_count_changed} changed, {total} total."))

        elif rule.rule_type == "new_results":
            matches = [r for r in results if r.change_status == "new"]
            if matches:
                events.append(_emit(db, agent, run, rule, None, "success",
                    f"{len(matches)} new result(s)", f"{agent.name} found {len(matches)} new result(s)."))

        elif rule.rule_type == "changed_results":
            matches = [r for r in results if r.change_status == "changed"]
            if matches:
                events.append(_emit(db, agent, run, rule, None, "info",
                    f"{len(matches)} result(s) changed", f"{agent.name} detected changes in {len(matches)} result(s)."))

        elif rule.rule_type == "high_priority_match":
            min_relevance = float(cfg.get("min_relevance", 0.8))
            matches = [r for r in results if r.relevance_score >= min_relevance]
            for r in matches:
                r.priority_flag = True
            if matches:
                events.append(_emit(db, agent, run, rule, matches[0].id, "warning",
                    f"{len(matches)} high-priority match(es)", f"{agent.name}: {matches[0].title}"))

        elif rule.rule_type == "deadline_approaching":
            days_before = int(cfg.get("days_before", 7))
            now = datetime.now(timezone.utc)
            for r in results:
                fields = from_json(r.fields_json, {})
                for fkey in _DEADLINE_KEYS:
                    val = fields.get(fkey)
                    if not val:
                        continue
                    d = parse_date(val)
                    if d and 0 <= (d - now).days <= days_before:
                        events.append(_emit(db, agent, run, rule, r.id, "warning",
                            f"Deadline approaching: {r.title}",
                            f"{fkey.replace('_', ' ')} is {val} ({(d - now).days} day(s) away)."))
                    break

        elif rule.rule_type == "run_error":
            if run.status == "failed":
                events.append(_emit(db, agent, run, rule, None, "error", "Run failed",
                    run.error_message or "Run failed for an unknown reason."))

    return events


def _get_or_create_notification_settings(db: Session, workspace_id: int) -> NotificationSettings:
    row = db.query(NotificationSettings).filter_by(workspace_id=workspace_id).first()
    if row is None:
        row = NotificationSettings(workspace_id=workspace_id)
        db.add(row)
        db.flush()
    return row


def _executive_summary(new_results: list[Result], changed_results: list[Result], high_priority: list[Result]) -> str:
    parts = []
    if new_results:
        headline = new_results[0].title
        extra = f" — including \"{headline}\"" if headline else ""
        parts.append(f"{len(new_results)} new finding(s){extra}")
    if changed_results:
        parts.append(f"{len(changed_results)} result(s) changed")
    if high_priority:
        parts.append(f"{len(high_priority)} high-priority match(es)")
    if not parts:
        return "No new or changed findings this run."
    return "; ".join(parts) + "."


def _build_run_message(agent: Agent, template: TemplateSpec, run: AgentRun, results: list[Result]) -> str:
    new_results = [r for r in results if r.change_status == "new"]
    changed_results = [r for r in results if r.change_status == "changed"]
    high_priority = [r for r in results if r.priority_flag]
    stats = from_json(run.stats_json, {})
    status_label = {"completed": "Success", "partial": "Partial success",
                   "failed": "Failed", "cancelled": "Cancelled"}.get(run.status, run.status)

    upcoming_deadlines = []
    now = datetime.now(timezone.utc)
    for r in results:
        fields = from_json(r.fields_json, {})
        for fkey in _DEADLINE_KEYS:
            val = fields.get(fkey)
            if val:
                d = parse_date(val)
                if d and 0 <= (d - now).days <= 30:
                    upcoming_deadlines.append(f"{sanitize_for_slack(r.title)}: {fkey.replace('_', ' ')} {val}")
                break

    base_url = app_settings.app_base_url.rstrip("/") if app_settings.app_base_url else ""
    run_url = f"{base_url}/agents/{agent.id}?run={run.id}" if base_url else f"/agents/{agent.id}?run={run.id}"

    total_seconds = int(run.duration_seconds or 0)
    duration_label = f"{total_seconds // 60}m {total_seconds % 60}s" if total_seconds >= 60 else f"{total_seconds}s"

    lines = [
        f"Agent completed: {sanitize_for_slack(agent.name)}",
        f"Type: {template.name}",
        f"Status: {status_label}",
        f"Started: {run.started_at}   Completed: {run.completed_at}   Duration: {duration_label}",
        f"New findings: {len(new_results)}   Changed findings: {len(changed_results)}   "
        f"High-priority matches: {len(high_priority)}",
        f"Sources checked: {stats.get('sources_touched', 0)}",
    ]
    if run.error_message:
        lines.append(f"Errors/inaccessible sources: {sanitize_for_slack(run.error_message)[:200]}")
    if upcoming_deadlines:
        lines.append("Upcoming deadlines: " + "; ".join(upcoming_deadlines[:3]))
    lines.append(f"Summary: {sanitize_for_slack(_executive_summary(new_results, changed_results, high_priority))}")
    lines.append(f"View results: {run_url}")
    lines.append(f"Run ID: {run.id}")
    return "\n".join(lines)


def deliver_alert_events(db: Session, agent: Agent, template: TemplateSpec, run: AgentRun,
                         results: list[Result], events: list[AlertEvent]) -> None:
    """Called ONLY after the run has reached a terminal state and been committed.
    A Slack failure here never affects run.status — that's already finalized."""
    ws_settings = _get_or_create_notification_settings(db, agent.workspace_id)
    if not ws_settings.slack_enabled:
        db.commit()
        return

    for event in events:
        rule = db.get(AlertRule, event.rule_id) if event.rule_id else None
        if rule is None or rule.channel != "slack":
            continue
        setting_field = _RULE_TO_SETTING.get(rule.rule_type)
        if setting_field and not getattr(ws_settings, setting_field, True):
            continue

        idem_key = f"{agent.id}:{run.id}:{rule.rule_type}"
        delivery = db.query(NotificationDelivery).filter_by(idempotency_key=idem_key).first()
        if delivery and delivery.status in ("sent", "skipped_disabled"):
            continue
        if delivery is None:
            delivery = NotificationDelivery(agent_id=agent.id, run_id=run.id,
                                            notification_type=rule.rule_type, idempotency_key=idem_key)
            db.add(delivery)
            db.flush()

        if not slack_configured():
            delivery.status = "skipped_disabled"
            db.commit()
            continue

        if rule.rule_type == "run_completed":
            status_label = {"completed": "Success", "partial": "Partial success",
                            "failed": "Failed", "cancelled": "Cancelled"}.get(run.status, run.status)
            title = f"{sanitize_for_slack(agent.name)} — {status_label}"
            message = _build_run_message(agent, template, run, results)
            severity = _RUN_STATUS_SEVERITY.get(run.status, "info")
        else:
            title = sanitize_for_slack(event.title)
            message = sanitize_for_slack(event.message)
            severity = event.severity

        ok, detail = send_slack_notification(
            event_type=f"agent_{rule.rule_type}", severity=severity, title=title, message=message)

        delivery.attempt_count += 1
        delivery.last_attempt_at = _utcnow()
        delivery.status = "sent" if ok else "failed"
        delivery.slack_channel = app_settings.slack_channel
        delivery.payload_json = to_json({"title": title, "message": message})
        if not ok:
            delivery.last_error = detail[:500]
        event.delivered = ok
        db.commit()
