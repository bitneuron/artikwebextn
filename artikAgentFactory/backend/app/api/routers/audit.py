from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.audit import record_audit
from app.auth.deps import require_role
from app.core.database import get_db
from app.core.utils import from_json
from app.models.audit_event import AuditEvent
from app.models.user import User

router = APIRouter(prefix="/api/audit-events", tags=["audit"])


def _out(e: AuditEvent) -> dict:
    return {
        "id": e.id, "ts": e.ts, "actor_user_id": e.actor_user_id, "actor_label": e.actor_label,
        "action": e.action, "resource_type": e.resource_type, "resource_id": e.resource_id,
        "outcome": e.outcome, "request_id": e.request_id, "ip_address": e.ip_address,
        "metadata": from_json(e.metadata_json, {}),
    }


@router.get("")
def list_audit_events(
    request: Request, db: Session = Depends(get_db), actor: User = Depends(require_role("administrator")),
    action: str | None = None, resource_type: str | None = None, outcome: str | None = None,
    limit: int = Query(100, le=500), offset: int = 0,
):
    stmt = select(AuditEvent)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if resource_type:
        stmt = stmt.where(AuditEvent.resource_type == resource_type)
    if outcome:
        stmt = stmt.where(AuditEvent.outcome == outcome)
    stmt = stmt.order_by(AuditEvent.ts.desc()).limit(limit).offset(offset)
    rows = list(db.execute(stmt).scalars().all())
    # Viewing the audit log is itself audited.
    record_audit(db, actor=actor, action="audit.view", resource_type="audit", outcome="success", request=request)
    db.commit()
    return [_out(e) for e in rows]
