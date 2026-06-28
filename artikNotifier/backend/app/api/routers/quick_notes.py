"""Quick Notes API — lightweight capture, search/filter, lifecycle, and one-click
conversion to a Reminder. All endpoints require auth and are scoped to the caller."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.enums import NOTE_CATEGORIES, Priority, QuickNoteStatus
from app.models.user import User
from app.schemas.dashboard import Message
from app.schemas.quick_note import (ConvertResult, QuickNoteCreate, QuickNoteOut,
                                    QuickNoteUpdate)
from app.services.quick_note_service import QuickNoteNotFound, QuickNoteService

router = APIRouter(prefix="/api/notes", tags=["quick-notes"])


def _svc(db: Session) -> QuickNoteService:
    return QuickNoteService(db)


@router.get("/options")
def note_options():
    """Category / priority / status / sort metadata for the Quick Notes UI."""
    return {
        "categories": NOTE_CATEGORIES,
        "priorities": [p.value for p in Priority],
        "statuses": [s.value for s in QuickNoteStatus],
        "sorts": ["created_at", "updated_at", "due_date", "title"],
    }


@router.get("", response_model=list[QuickNoteOut])
def list_notes(
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
    status: str | None = None, category: str | None = None, priority: str | None = None,
    tag: str | None = None, search: str | None = None,
    due_from: date | None = None, due_to: date | None = None,
    sort: str = "created_at", order: str = "desc",
    limit: int = Query(50, le=200), offset: int = 0,
):
    svc = _svc(db)
    rows = svc.list(user.id, status=status, category=category, priority=priority,
                    tag=tag, search=search, due_from=due_from, due_to=due_to,
                    sort=sort, order=order, limit=limit, offset=offset)
    return [svc.to_out(n) for n in rows]


@router.post("", response_model=QuickNoteOut, status_code=201)
def create_note(body: QuickNoteCreate, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    svc = _svc(db)
    return svc.to_out(svc.create(user.id, body))


@router.get("/{note_id}", response_model=QuickNoteOut)
def get_note(note_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = _svc(db)
    try:
        return svc.to_out(svc.get(user.id, note_id))
    except QuickNoteNotFound:
        raise HTTPException(404, "note not found")


@router.put("/{note_id}", response_model=QuickNoteOut)
def update_note(note_id: int, body: QuickNoteUpdate, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    svc = _svc(db)
    try:
        return svc.to_out(svc.update(user.id, note_id, body))
    except QuickNoteNotFound:
        raise HTTPException(404, "note not found")


@router.delete("/{note_id}", response_model=Message)
def delete_note(note_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        _svc(db).delete(user.id, note_id)
        return {"detail": "deleted"}
    except QuickNoteNotFound:
        raise HTTPException(404, "note not found")


def _action(action: str):
    def handler(note_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
        svc = _svc(db)
        try:
            return svc.to_out(getattr(svc, action)(user.id, note_id))
        except QuickNoteNotFound:
            raise HTTPException(404, "note not found")
    return handler


router.add_api_route("/{note_id}/complete", _action("complete"), methods=["POST"], response_model=QuickNoteOut)
router.add_api_route("/{note_id}/archive", _action("archive"), methods=["POST"], response_model=QuickNoteOut)
router.add_api_route("/{note_id}/restore", _action("restore"), methods=["POST"], response_model=QuickNoteOut)


@router.post("/{note_id}/convert", response_model=ConvertResult)
def convert_note(note_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = _svc(db)
    try:
        note, reminder_id = svc.convert_to_reminder(user.id, note_id)
        return {"note": svc.to_out(note), "reminder_id": reminder_id}
    except QuickNoteNotFound:
        raise HTTPException(404, "note not found")
