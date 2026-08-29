from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.audit import record_audit
from app.auth.deps import get_current_active_user, get_note_or_404, get_result_or_404, require_agent_access
from app.core.database import get_db
from app.models.agent import Agent
from app.models.note import Note
from app.models.result import Result
from app.models.user import User
from app.repositories.result_repo import ResultRepository
from app.schemas.result import NoteIn
from app.services.result_service import ResultService

router = APIRouter(tags=["results"])


def _svc(db: Session) -> ResultService:
    return ResultService(db)


@router.get("/api/agents/{agent_id}/results")
def list_results(
    agent_id: int, db: Session = Depends(get_db), agent: Agent = Depends(require_agent_access("viewer")),
    category: str | None = None, change_status: str | None = None, is_saved: bool | None = None,
    is_dismissed: bool | None = None, min_relevance: float | None = None, search: str | None = None,
    sort: str = "created_at", order: str = "desc", limit: int = Query(100, le=500), offset: int = 0,
):
    svc = _svc(db)
    rows = ResultRepository(db).query(
        agent_id, category=category, change_status=change_status, is_saved=is_saved,
        is_dismissed=is_dismissed, min_relevance=min_relevance, search=search,
        sort=sort, order=order, limit=limit, offset=offset)
    return [svc.to_out(r) for r in rows]


@router.get("/api/agents/{agent_id}/results/export")
def export_results(
    agent_id: int, request: Request, db: Session = Depends(get_db),
    agent: Agent = Depends(require_agent_access("researcher")),
    user: User = Depends(get_current_active_user),
    fmt: str = Query("csv", pattern="^(csv|json)$"),
):
    rows = ResultRepository(db).query(agent_id, limit=5000)
    svc = _svc(db)
    record_audit(db, actor=user, action="export.create", resource_type="agent", resource_id=agent_id,
                outcome="success", request=request, metadata={"format": fmt, "row_count": len(rows)})
    db.commit()
    if fmt == "json":
        return [svc.to_out(r) for r in rows]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["title", "url", "source_name", "category", "relevance_score",
                     "confidence_score", "source_credibility", "change_status", "created_at"])
    for r in rows:
        writer.writerow([r.title, r.url, r.source_name, r.category, r.relevance_score,
                         r.confidence_score, r.source_credibility, r.change_status, r.created_at])
    buf.seek(0)
    return StreamingResponse(buf, media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="agent-{agent_id}-results.csv"'})


@router.get("/api/agents/{agent_id}/sources")
def agent_sources(agent_id: int, db: Session = Depends(get_db), agent: Agent = Depends(require_agent_access("viewer"))):
    return _svc(db).sources_summary(agent_id)


@router.get("/api/results/{result_id}")
def get_result(db: Session = Depends(get_db), result: Result = Depends(get_result_or_404("viewer"))):
    return _svc(db).to_detail(result)


@router.post("/api/results/{result_id}/save")
def save_result(request: Request, db: Session = Depends(get_db),
                result: Result = Depends(get_result_or_404("researcher"))):
    out = _svc(db).save(result.id, True)
    return _svc(db).to_out(out)


@router.post("/api/results/{result_id}/unsave")
def unsave_result(db: Session = Depends(get_db), result: Result = Depends(get_result_or_404("researcher"))):
    out = _svc(db).save(result.id, False)
    return _svc(db).to_out(out)


@router.post("/api/results/{result_id}/dismiss")
def dismiss_result(request: Request, db: Session = Depends(get_db),
                   result: Result = Depends(get_result_or_404("researcher")),
                   user: User = Depends(get_current_active_user)):
    out = _svc(db).dismiss(result.id, True)
    record_audit(db, actor=user, action="result.dismiss", resource_type="result",
                resource_id=result.id, outcome="success", request=request)
    db.commit()
    return _svc(db).to_out(out)


@router.post("/api/results/{result_id}/undismiss")
def undismiss_result(db: Session = Depends(get_db), result: Result = Depends(get_result_or_404("researcher"))):
    out = _svc(db).dismiss(result.id, False)
    return _svc(db).to_out(out)


@router.get("/api/results/{result_id}/notes")
def list_notes(db: Session = Depends(get_db), result: Result = Depends(get_result_or_404("viewer"))):
    return _svc(db).to_detail(result)["notes"]


@router.post("/api/results/{result_id}/notes", status_code=201)
def create_note(body: NoteIn, request: Request, db: Session = Depends(get_db),
                result: Result = Depends(get_result_or_404("researcher")),
                user: User = Depends(get_current_active_user)):
    n = _svc(db).add_note(result.id, body.body)
    record_audit(db, actor=user, action="note.create", resource_type="note",
                resource_id=n.id, outcome="success", request=request, metadata={"result_id": result.id})
    db.commit()
    return {"id": n.id, "result_id": n.result_id, "body": n.body, "created_at": n.created_at, "updated_at": n.updated_at}


@router.put("/api/notes/{note_id}")
def update_note(body: NoteIn, request: Request, db: Session = Depends(get_db),
                note: Note = Depends(get_note_or_404("researcher")),
                user: User = Depends(get_current_active_user)):
    n = _svc(db).update_note(note.id, body.body)
    record_audit(db, actor=user, action="note.update", resource_type="note",
                resource_id=n.id, outcome="success", request=request)
    db.commit()
    return {"id": n.id, "result_id": n.result_id, "body": n.body, "created_at": n.created_at, "updated_at": n.updated_at}


@router.delete("/api/notes/{note_id}")
def delete_note(request: Request, db: Session = Depends(get_db),
                note: Note = Depends(get_note_or_404("researcher")),
                user: User = Depends(get_current_active_user)):
    _svc(db).delete_note(note.id)
    record_audit(db, actor=user, action="note.delete", resource_type="note",
                resource_id=note.id, outcome="success", request=request)
    db.commit()
    return {"detail": "deleted"}
