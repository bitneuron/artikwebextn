from __future__ import annotations

from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.utils import from_json
from app.models.note import Note
from app.models.result import Result
from app.repositories.result_repo import ResultRepository


class ResultNotFound(Exception):
    pass


class ResultService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ResultRepository(db)

    def to_out(self, r: Result) -> dict:
        return {
            "id": r.id, "agent_id": r.agent_id, "title": r.title, "summary": r.summary, "url": r.url,
            "source_name": r.source_name, "published_or_updated_at": r.published_or_updated_at,
            "relevance_score": r.relevance_score, "confidence_score": r.confidence_score,
            "source_credibility": r.source_credibility, "category": r.category,
            "fields": from_json(r.fields_json, {}), "change_status": r.change_status,
            "changed_fields": from_json(r.changed_fields_json, {}) if r.changed_fields_json else {},
            "is_saved": r.is_saved, "is_dismissed": r.is_dismissed, "priority_flag": r.priority_flag,
            "first_seen_run_id": r.first_seen_run_id, "last_seen_run_id": r.last_seen_run_id,
            "created_at": r.created_at, "updated_at": r.updated_at,
        }

    def to_detail(self, r: Result) -> dict:
        out = self.to_out(r)
        out["sources"] = [
            {"id": s.id, "url": s.url, "title": s.title, "retrieved_at": s.retrieved_at, "snippet": s.snippet}
            for s in r.sources
        ]
        out["notes"] = [
            {"id": n.id, "result_id": n.result_id, "body": n.body, "created_at": n.created_at, "updated_at": n.updated_at}
            for n in r.notes
        ]
        return out

    def get(self, result_id: int) -> Result:
        r = self.repo.get(result_id)
        if not r:
            raise ResultNotFound()
        return r

    def save(self, result_id: int, saved: bool) -> Result:
        r = self.get(result_id)
        r.is_saved = saved
        self.db.commit()
        self.db.refresh(r)
        return r

    def dismiss(self, result_id: int, dismissed: bool) -> Result:
        r = self.get(result_id)
        r.is_dismissed = dismissed
        self.db.commit()
        self.db.refresh(r)
        return r

    def add_note(self, result_id: int, body: str) -> Note:
        self.get(result_id)  # 404 if missing
        note = Note(result_id=result_id, body=body)
        self.db.add(note)
        self.db.commit()
        self.db.refresh(note)
        return note

    def update_note(self, note_id: int, body: str) -> Note:
        note = self.db.get(Note, note_id)
        if not note:
            raise ResultNotFound()
        note.body = body
        self.db.commit()
        self.db.refresh(note)
        return note

    def delete_note(self, note_id: int) -> None:
        note = self.db.get(Note, note_id)
        if not note:
            raise ResultNotFound()
        self.db.delete(note)
        self.db.commit()

    def sources_summary(self, agent_id: int) -> list[dict]:
        rows = self.db.execute(
            select(Result.source_name, Result.url, Result.source_credibility)
            .where(Result.agent_id == agent_id, Result.is_dismissed.is_(False))
        ).all()
        by_domain: dict[str, dict] = {}
        for source_name, url, credibility in rows:
            domain = urlsplit(url).netloc.lower().removeprefix("www.") if url else "unknown"
            key = domain or "unknown"
            entry = by_domain.setdefault(key, {"source_name": source_name, "domain": key, "count": 0, "credibility": credibility})
            entry["count"] += 1
        return sorted(by_domain.values(), key=lambda e: -e["count"])
