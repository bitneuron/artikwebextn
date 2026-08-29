"""Run execution pipeline entry point — the single function called by both "Run Now"
and the scheduler. Orchestrates: query_builder -> web_search -> extraction -> dedup ->
change_detection -> persist -> alerts -> finalize (see the approved plan)."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.utils import from_json, to_json
from app.models.agent import Agent
from app.models.run import AgentRun
from app.repositories.result_repo import ResultRepository
from app.services.email_client import send_email
from app.services.pipeline.alerts import deliver_alert_events, run_alert_rules
from app.services.pipeline.change_detector import detect_changes
from app.services.pipeline.dedup import dedup
from app.services.pipeline.extractor import extract_structured
from app.services.pipeline.log_scrub import log_run
from app.services.pipeline.persist import persist
from app.services.pipeline.query_builder import build_queries
from app.services.pipeline.searcher import web_search_pass
from app.templates.registry import get_template
from app.templates.spec import TemplateSpec


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def execute_run(db: Session, agent: Agent, trigger: str) -> AgentRun:
    template = get_template(agent.template_id)
    if template is None:
        run = AgentRun(agent_id=agent.id, trigger=trigger, status="failed",
                       started_at=_utcnow(), completed_at=_utcnow(), duration_seconds=0.0,
                       error_message=f"Unknown template: {agent.template_id}")
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    run = AgentRun(agent_id=agent.id, trigger=trigger, status="running", started_at=_utcnow())
    db.add(run)
    db.commit()
    db.refresh(run)

    started = time.monotonic()

    if template.kind == "action":
        return _execute_action_run(db, agent, template, run, started)

    stats: dict = {}
    had_errors = False
    results: list = []
    events: list = []

    try:
        filters = from_json(agent.filters_json, {})
        profile = from_json(agent.profile_json, None) if agent.profile_json else None
        try:
            max_results = int(filters.get("max_results") or 20)
        except (TypeError, ValueError):
            max_results = 20

        queries = build_queries(agent.objective, filters, profile, settings.max_queries_per_run)
        run.queries_json = to_json(queries)
        db.commit()
        log_run(db, run.id, "query_build", f"{len(queries)} quer(y/ies): {queries}")

        raw_findings, sources_touched, search_had_errors = web_search_pass(queries, settings.web_search_max_uses)
        had_errors = had_errors or search_had_errors
        stats["sources_touched"] = sources_touched
        stats["queries_succeeded"] = len(raw_findings)
        stats["queries_total"] = len(queries)
        log_run(db, run.id, "web_search", f"{len(raw_findings)}/{len(queries)} quer(y/ies) succeeded, {sources_touched} source(s) touched")

        try:
            candidates = extract_structured(raw_findings, template, agent.objective, max_results)
            log_run(db, run.id, "extraction", f"{len(candidates)} candidate finding(s) before validation")
        except Exception as e:  # noqa: BLE001
            log_run(db, run.id, "extraction", f"extraction failed: {e}", level="error")
            candidates = []
            had_errors = True

        before = len(candidates)
        candidates = [c for c in candidates if (c.get("url") or "").strip()]
        dropped = before - len(candidates)
        if dropped:
            log_run(db, run.id, "extraction", f"dropped {dropped} finding(s) with no source URL", level="warn")

        deduped = dedup(candidates)
        stats["duplicates_dropped"] = len(candidates) - len(deduped)
        log_run(db, run.id, "dedup", f"{len(deduped)} unique result(s) ({stats['duplicates_dropped']} duplicate(s) dropped)")

        result_repo = ResultRepository(db)
        existing_by_key = {r.dedup_key: r for r in result_repo.all_for_agent(agent.id, include_dismissed=False)}
        deduped, counts = detect_changes(existing_by_key, deduped, template, run.id)
        log_run(db, run.id, "change_detection",
               f"new={counts['new']} changed={counts['changed']} unchanged={counts['unchanged']}")

        results = persist(db, agent, run, deduped)
        db.commit()
        log_run(db, run.id, "persist", f"persisted {len(results)} result(s)")

        run.result_count_new = counts["new"]
        run.result_count_changed = counts["changed"]
        run.result_count_unchanged = counts["unchanged"]
        run.result_count_total = len(results)
        run.status = "partial" if had_errors else "completed"
        run.stats_json = to_json(stats)

        # Evaluation only — creates AlertEvent rows. Actual Slack delivery happens
        # below, strictly after the run is finalized and committed (never mid-run).
        events = run_alert_rules(db, agent, run, results)
        db.commit()
        log_run(db, run.id, "alerts", f"{len(events)} alert(s) evaluated")

    except Exception as e:  # noqa: BLE001
        db.rollback()
        db.refresh(run)
        run.status = "partial" if run.result_count_total else "failed"
        run.error_message = str(e)[:2000]
        try:
            log_run(db, run.id, "persist", f"run failed: {e}", level="error")
        except Exception:  # noqa: BLE001
            pass
        try:
            events = run_alert_rules(db, agent, run, [])
        except Exception:  # noqa: BLE001
            events = []

    finally:
        run.completed_at = _utcnow()
        run.duration_seconds = time.monotonic() - started
        agent.last_run_id = run.id
        agent.last_run_at = run.completed_at
        agent.last_run_status = run.status
        db.commit()
        db.refresh(run)

    # Delivery happens ONLY after the run's terminal state is committed above — a
    # Slack failure here can never retroactively change run.status.
    try:
        deliver_alert_events(db, agent, template, run, results, events)
    except Exception:  # noqa: BLE001
        pass

    return run


def _execute_action_run(db: Session, agent: Agent, template: TemplateSpec, run: AgentRun, started: float) -> AgentRun:
    """Run path for kind="action" templates — no web search, no Results, the run
    itself performs a one-off side effect. Currently only email_scheduler; a second
    action template would add a branch here rather than a new pipeline."""
    events: list = []
    try:
        if agent.template_id != "email_scheduler":
            raise ValueError(f"no action handler for template: {agent.template_id}")

        filters = from_json(agent.filters_json, {})
        to_email = (filters.get("to_email") or "").strip()
        subject = (filters.get("subject") or "").strip() or agent.name
        message = filters.get("message") or ""
        if not to_email:
            raise ValueError("no recipient configured (\"to\" is required)")

        ok, detail = send_email(to_email=to_email, subject=subject, body=message)
        log_run(db, run.id, "email", detail, level="info" if ok else "error")
        run.status = "completed" if ok else "failed"
        if not ok:
            run.error_message = detail[:2000]
        run.result_count_new = run.result_count_changed = run.result_count_unchanged = run.result_count_total = 0

    except Exception as e:  # noqa: BLE001
        db.rollback()
        db.refresh(run)
        run.status = "failed"
        run.error_message = str(e)[:2000]
        try:
            log_run(db, run.id, "email", f"run failed: {e}", level="error")
        except Exception:  # noqa: BLE001
            pass

    finally:
        run.completed_at = _utcnow()
        run.duration_seconds = time.monotonic() - started
        agent.last_run_id = run.id
        agent.last_run_at = run.completed_at
        agent.last_run_status = run.status
        db.commit()
        db.refresh(run)

    try:
        events = run_alert_rules(db, agent, run, [])
        db.commit()
    except Exception:  # noqa: BLE001
        events = []
    try:
        deliver_alert_events(db, agent, template, run, [], events)
    except Exception:  # noqa: BLE001
        pass

    return run


def run_to_out(run: AgentRun) -> dict:
    return {
        "id": run.id, "agent_id": run.agent_id, "trigger": run.trigger, "status": run.status,
        "started_at": run.started_at, "completed_at": run.completed_at,
        "duration_seconds": run.duration_seconds,
        "result_count_new": run.result_count_new, "result_count_changed": run.result_count_changed,
        "result_count_unchanged": run.result_count_unchanged, "result_count_total": run.result_count_total,
        "error_message": run.error_message, "queries": from_json(run.queries_json, []),
        "stats": from_json(run.stats_json, {}), "created_at": run.created_at,
    }
