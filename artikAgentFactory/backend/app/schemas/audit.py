from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AuditEventOut(BaseModel):
    id: int
    ts: datetime
    actor_user_id: int | None
    actor_label: str
    action: str
    resource_type: str
    resource_id: str | None
    outcome: str
    request_id: str | None
    ip_address: str | None
    metadata: dict = {}
