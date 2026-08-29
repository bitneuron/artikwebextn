from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AgentAccessIn(BaseModel):
    user_id: int
    access_level: str  # viewer|researcher|manager


class AgentAccessOut(BaseModel):
    id: int
    agent_id: int
    user_id: int
    user_email: str
    access_level: str
    granted_by: int
    created_at: datetime
