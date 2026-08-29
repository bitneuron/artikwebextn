from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth.audit import record_audit
from app.auth.deps import require_role
from app.core.database import get_db
from app.models.notification_settings import NotificationSettings
from app.models.user import User
from app.schemas.notification_settings import NotificationSettingsOut, NotificationSettingsUpdate
from app.services.notify_client import slack_configured

router = APIRouter(prefix="/api/notification-settings", tags=["notification-settings"])


def _get_or_create(db: Session, workspace_id: int) -> NotificationSettings:
    row = db.query(NotificationSettings).filter_by(workspace_id=workspace_id).first()
    if row is None:
        row = NotificationSettings(workspace_id=workspace_id)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _out(row: NotificationSettings) -> dict:
    return {
        "workspace_id": row.workspace_id, "slack_enabled": row.slack_enabled,
        "notify_on_run_completed": row.notify_on_run_completed,
        "notify_on_new_results": row.notify_on_new_results,
        "notify_on_changed_results": row.notify_on_changed_results,
        "notify_on_high_priority": row.notify_on_high_priority,
        "notify_on_deadline_approaching": row.notify_on_deadline_approaching,
        "notify_on_run_error": row.notify_on_run_error,
        "min_severity": row.min_severity, "slack_configured": slack_configured(),
        "updated_at": row.updated_at,
    }


@router.get("", response_model=NotificationSettingsOut)
def get_settings(db: Session = Depends(get_db), user: User = Depends(require_role("administrator"))):
    return _out(_get_or_create(db, user.workspace_id))


@router.put("", response_model=NotificationSettingsOut)
def update_settings(body: NotificationSettingsUpdate, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(require_role("administrator"))):
    row = _get_or_create(db, user.workspace_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(row, field, value)
    row.updated_by = user.id
    record_audit(db, actor=user, action="notification_setting.update", resource_type="notification_settings",
                resource_id=row.id, outcome="success", request=request,
                metadata=body.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(row)
    return _out(row)
