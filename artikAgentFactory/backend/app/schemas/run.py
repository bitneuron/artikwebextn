from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RunOut(BaseModel):
    id: int
    agent_id: int
    trigger: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    duration_seconds: float | None
    result_count_new: int
    result_count_changed: int
    result_count_unchanged: int
    result_count_total: int
    error_message: str | None
    queries: list[str] = []
    stats: dict = {}
    created_at: datetime


class RunLogOut(BaseModel):
    id: int
    run_id: int
    ts: datetime
    level: str
    stage: str
    message: str
