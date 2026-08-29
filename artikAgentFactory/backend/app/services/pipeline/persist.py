"""Stage 6 — upsert Result/ResultSource rows keyed by dedup_key."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.utils import to_json
from app.models.agent import Agent
from app.models.result import Result, ResultSource
from app.models.run import AgentRun
from app.repositories.result_repo import ResultRepository
from app.services.pipeline.dates import parse_date


def persist(db: Session, agent: Agent, run: AgentRun, deduped: list[dict]) -> list[Result]:
    repo = ResultRepository(db)
    saved: list[Result] = []

    for c in deduped:
        key = c["_dedup_key"]
        row = repo.get_by_dedup_key(agent.id, key)
        published = parse_date(c.get("published_or_updated_at"))
        changed_fields = c.get("_changed_fields")

        if row is None:
            row = Result(agent_id=agent.id, dedup_key=key, title=c.get("title") or "Untitled",
                         first_seen_run_id=c["_first_seen_run_id"])
            db.add(row)

        row.title = c.get("title") or row.title
        row.summary = c.get("summary")
        row.url = c.get("url")
        row.source_name = c.get("source_name")
        row.published_or_updated_at = published
        row.relevance_score = float(c.get("relevance_score") or 0)
        row.confidence_score = float(c.get("confidence_score") or 0)
        row.source_credibility = c.get("source_credibility") or "medium"
        row.category = c.get("category") or "general"
        row.fields_json = to_json(c.get("fields") or {})
        row.change_status = c["_change_status"]
        row.changed_fields_json = to_json(changed_fields) if changed_fields else None
        row.last_seen_run_id = c["_last_seen_run_id"]
        db.flush()

        for s in list(row.sources):
            db.delete(s)
        db.flush()
        source_list = c.get("sources") or []
        if not any((s.get("url") or "") == row.url for s in source_list):
            source_list = [{"url": row.url, "title": row.source_name}] + source_list
        for src in source_list:
            url = (src.get("url") or "").strip()
            if url:
                db.add(ResultSource(result_id=row.id, url=url, title=src.get("title")))

        saved.append(row)

    db.flush()
    return saved
