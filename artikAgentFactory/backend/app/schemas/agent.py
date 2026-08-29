from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AlertRuleIn(BaseModel):
    rule_type: str
    channel: str = "in_app"
    config: dict = Field(default_factory=dict)
    is_enabled: bool = True


class AlertRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    agent_id: int
    rule_type: str
    channel: str
    is_enabled: bool
    config: dict
    created_at: datetime


class AgentCreate(BaseModel):
    template_id: str
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    objective: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    result_language: str = "en"
    time_zone: str = "UTC"
    filters: dict = Field(default_factory=dict)
    profile: dict | None = None
    schedule: dict = Field(default_factory=lambda: {"mode": "manual"})
    is_schedule_enabled: bool = False
    alert_rules: list[AlertRuleIn] = Field(default_factory=list)
    status: str = "active"
    visibility: str = "private"  # private|shared
    run_immediately: bool = False


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    objective: str | None = None
    tags: list[str] | None = None
    result_language: str | None = None
    time_zone: str | None = None
    filters: dict | None = None
    profile: dict | None = None
    schedule: dict | None = None
    is_schedule_enabled: bool | None = None
    alert_rules: list[AlertRuleIn] | None = None
    status: str | None = None
    visibility: str | None = None


class AgentOut(BaseModel):
    id: int
    template_id: int | str
    owner_id: int
    workspace_id: int
    visibility: str
    name: str
    description: str | None
    objective: str
    status: str
    tags: list[str]
    result_language: str
    time_zone: str
    filters: dict
    profile: dict | None
    schedule: dict
    is_schedule_enabled: bool
    last_run_id: int | None
    last_run_at: datetime | None
    last_run_status: str | None
    next_run_at: datetime | None
    alert_rules: list[AlertRuleOut]
    created_at: datetime
    updated_at: datetime


class AgentListItem(BaseModel):
    id: int
    template_id: str
    owner_id: int
    visibility: str
    name: str
    description: str | None
    status: str
    tags: list[str]
    is_schedule_enabled: bool
    last_run_at: datetime | None
    last_run_status: str | None
    next_run_at: datetime | None
    result_count_total: int = 0
    result_count_new: int = 0
    result_count_changed: int = 0
    high_priority_count: int = 0
    can_manage: bool = True
    can_run: bool = True
    created_at: datetime
    updated_at: datetime
