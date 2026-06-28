"""Categories, tags, preferences, channels, and a manual scheduler trigger."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.enums import DEFAULT_CATEGORIES, Priority, Recurrence
from app.models.reminder import Category, Tag
from app.models.user import User, UserPreferences
from app.notifications.registry import available_channels
from app.schemas.notification import PreferencesOut, PreferencesUpdate

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/categories")
def categories(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Category).where(Category.user_id == user.id)).scalars().all()
    names = [c.name for c in rows] or DEFAULT_CATEGORIES
    return {"categories": names}


@router.get("/tags")
def tags(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Tag).where(Tag.user_id == user.id)).scalars().all()
    return {"tags": [t.name for t in rows]}


@router.get("/options")
def options():
    """Enum/option metadata for the frontend forms."""
    return {
        "categories": DEFAULT_CATEGORIES,
        "priorities": [p.value for p in Priority],
        "recurrences": [r.value for r in Recurrence],
        "channels": available_channels(),
        "all_channels": ["email", "in_app", "sms", "push", "slack", "teams", "discord", "whatsapp", "webhook"],
        "schedule_offsets": ["on_due", "1_day", "2_days", "3_days", "1_week", "2_weeks", "1_month"],
    }


@router.get("/preferences", response_model=PreferencesOut)
def get_preferences(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    prefs = user.preferences or db.execute(
        select(UserPreferences).where(UserPreferences.user_id == user.id)).scalar_one_or_none()
    if not prefs:
        prefs = UserPreferences(user_id=user.id)
        db.add(prefs); db.commit(); db.refresh(prefs)
    return prefs


@router.put("/preferences", response_model=PreferencesOut)
def update_preferences(body: PreferencesUpdate, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    prefs = db.execute(select(UserPreferences).where(
        UserPreferences.user_id == user.id)).scalar_one_or_none() or UserPreferences(user_id=user.id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(prefs, k, v)
    db.add(prefs); db.commit(); db.refresh(prefs)
    return prefs
