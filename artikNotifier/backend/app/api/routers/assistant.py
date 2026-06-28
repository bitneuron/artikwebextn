"""Artik Assistant chatbot API — operates ONLY on the authenticated user's data."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.dashboard import Message
from app.services.assistant_service import AssistantService

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class ChatOut(BaseModel):
    reply: str
    insights: list[str]


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    role: str
    content: str
    created_at: datetime


@router.post("/chat", response_model=ChatOut)
def chat(body: ChatIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return AssistantService(db, user).chat(body.message)


@router.get("/insights", response_model=list[str])
def insights(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return AssistantService(db, user).insights()


@router.get("/history", response_model=list[ChatMessageOut])
def history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return AssistantService(db, user).history()


@router.delete("/history", response_model=Message)
def clear_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    AssistantService(db, user).clear_history()
    return {"detail": "history cleared"}
