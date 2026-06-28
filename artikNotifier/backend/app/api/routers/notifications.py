from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.dashboard import Message
from app.schemas.notification import BellOut, NotificationOut
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _svc(db: Session) -> NotificationService:
    return NotificationService(db)


@router.get("", response_model=list[NotificationOut])
def list_notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db),
                       status: str | None = None, unread_only: bool = False,
                       search: str | None = None, limit: int = Query(50, le=200), offset: int = 0):
    return _svc(db).list(user.id, status=status, unread_only=unread_only,
                         search=search, limit=limit, offset=offset)


@router.get("/bell", response_model=BellOut)
def bell(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _svc(db).bell(user.id)


@router.post("/{notif_id}/read", response_model=NotificationOut)
def mark_read(notif_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = _svc(db).mark_read(user.id, notif_id)
    if not n:
        raise HTTPException(404, "notification not found")
    return n


@router.post("/read-all", response_model=Message)
def mark_all_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    count = _svc(db).mark_all_read(user.id)
    return {"detail": f"{count} marked read"}


@router.delete("/{notif_id}", response_model=Message)
def delete_notification(notif_id: int, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    if not _svc(db).delete(user.id, notif_id):
        raise HTTPException(404, "notification not found")
    return {"detail": "deleted"}
