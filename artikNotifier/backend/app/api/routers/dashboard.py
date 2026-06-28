from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.dashboard import CalendarOut, DashboardOut
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return DashboardService(db).dashboard(user.id)


@router.get("/calendar", response_model=CalendarOut)
def calendar(year: int | None = Query(default=None), month: int | None = Query(default=None),
             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    return DashboardService(db).calendar(user.id, year or now.year, month or now.month)
