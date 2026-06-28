from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.notifications.registry import available_channels

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "app": settings.app_name,
        "environment": settings.environment,
        "database": "ok" if db_ok else "error",
        "scheduler_enabled": settings.scheduler_enabled,
        "channels": available_channels(),
    }


@router.post("/scheduler/run")
def run_scheduler_now(user: User = Depends(require_admin)):
    """Manually trigger a global dispatch tick — admin only (it processes every
    user's due rules, so it must not be exposed to normal users)."""
    from app.scheduler.scheduler import run_once
    return run_once()
