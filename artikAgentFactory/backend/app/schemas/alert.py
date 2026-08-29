from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AlertEventOut(BaseModel):
    id: int
    agent_id: int
    run_id: int
    rule_id: int | None
    result_id: int | None
    severity: str
    title: str
    message: str
    delivered: bool
    created_at: datetime


class DashboardOut(BaseModel):
    total_agents: int
    active_agents: int
    paused_agents: int
    error_agents: int
    new_findings_7d: int
    high_priority_alerts: int
    sources_checked_7d: int
    upcoming_deadlines: int
    scheduler_running: bool
    recent_alerts: list[AlertEventOut]
