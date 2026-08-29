from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import require_agent_access
from app.core.database import get_db
from app.models.agent import Agent
from app.models.alert import AlertEvent
from app.schemas.alert import AlertEventOut

router = APIRouter(tags=["alerts"])


@router.get("/api/agents/{agent_id}/alert-events", response_model=list[AlertEventOut])
def list_alert_events(agent_id: int, db: Session = Depends(get_db),
                      agent: Agent = Depends(require_agent_access("viewer")),
                      limit: int = Query(50, le=200)):
    stmt = (select(AlertEvent).where(AlertEvent.agent_id == agent_id)
           .order_by(AlertEvent.created_at.desc()).limit(limit))
    return list(db.execute(stmt).scalars().all())
