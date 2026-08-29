from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ResultSourceOut(BaseModel):
    id: int
    url: str
    title: str | None
    retrieved_at: datetime
    snippet: str | None


class NoteOut(BaseModel):
    id: int
    result_id: int
    body: str
    created_at: datetime
    updated_at: datetime


class NoteIn(BaseModel):
    body: str


class ResultOut(BaseModel):
    id: int
    agent_id: int
    title: str
    summary: str | None
    url: str
    source_name: str | None
    published_or_updated_at: datetime | None
    relevance_score: float
    confidence_score: float
    source_credibility: str
    category: str
    fields: dict
    change_status: str
    changed_fields: dict
    is_saved: bool
    is_dismissed: bool
    priority_flag: bool
    first_seen_run_id: int | None
    last_seen_run_id: int | None
    created_at: datetime
    updated_at: datetime


class ResultDetailOut(ResultOut):
    sources: list[ResultSourceOut]
    notes: list[NoteOut]


class SourceSummaryOut(BaseModel):
    source_name: str | None
    domain: str
    count: int
    credibility: str
