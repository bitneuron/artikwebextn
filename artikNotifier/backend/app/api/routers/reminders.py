from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.dashboard import Message
from app.schemas.reminder import (ReminderCreate, ReminderOut, ReminderUpdate, SnoozeIn)
from app.services.reminder_service import ReminderNotFound, ReminderService

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


def _svc(db: Session) -> ReminderService:
    return ReminderService(db)


def _out(svc: ReminderService, r) -> dict:
    return svc.to_out(r)


@router.get("", response_model=list[ReminderOut])
def list_reminders(
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
    status: str | None = None, category: str | None = None, priority: str | None = None,
    search: str | None = None, sort: str = "due_at", order: str = "asc",
    limit: int = Query(100, le=500), offset: int = 0,
):
    svc = _svc(db)
    rows = svc.list(user.id, status=status, category=category, priority=priority,
                    search=search, sort=sort, order=order, limit=limit, offset=offset)
    return [_out(svc, r) for r in rows]


@router.post("", response_model=ReminderOut, status_code=201)
def create_reminder(body: ReminderCreate, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    svc = _svc(db)
    return _out(svc, svc.create(user.id, body))


@router.get("/{reminder_id}", response_model=ReminderOut)
def get_reminder(reminder_id: int, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    svc = _svc(db)
    try:
        return _out(svc, svc.get(user.id, reminder_id))
    except ReminderNotFound:
        raise HTTPException(404, "reminder not found")


@router.put("/{reminder_id}", response_model=ReminderOut)
def update_reminder(reminder_id: int, body: ReminderUpdate,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = _svc(db)
    try:
        return _out(svc, svc.update(user.id, reminder_id, body))
    except ReminderNotFound:
        raise HTTPException(404, "reminder not found")


@router.delete("/{reminder_id}", response_model=Message)
def delete_reminder(reminder_id: int, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    try:
        _svc(db).delete(user.id, reminder_id)
        return {"detail": "deleted"}
    except ReminderNotFound:
        raise HTTPException(404, "reminder not found")


def _action(action: str):
    def handler(reminder_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
        svc = _svc(db)
        try:
            return _out(svc, getattr(svc, action)(user.id, reminder_id))
        except ReminderNotFound:
            raise HTTPException(404, "reminder not found")
    return handler


router.add_api_route("/{reminder_id}/complete", _action("complete"), methods=["POST"], response_model=ReminderOut)
router.add_api_route("/{reminder_id}/archive", _action("archive"), methods=["POST"], response_model=ReminderOut)
router.add_api_route("/{reminder_id}/restore", _action("restore"), methods=["POST"], response_model=ReminderOut)
router.add_api_route("/{reminder_id}/duplicate", _action("duplicate"), methods=["POST"], response_model=ReminderOut)


@router.post("/{reminder_id}/snooze", response_model=ReminderOut)
def snooze(reminder_id: int, body: SnoozeIn, user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    svc = _svc(db)
    try:
        return _out(svc, svc.snooze(user.id, reminder_id, minutes=body.minutes, until=body.until))
    except ReminderNotFound:
        raise HTTPException(404, "reminder not found")
