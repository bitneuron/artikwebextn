from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# Deliberately not pydantic's EmailStr: the email_validator library it wraps rejects
# RFC 2606/6762 reserved TLDs (.test, .local, .example, ...) outright, which blocks
# legitimate internal/corporate domains and every local test fixture. This app never
# sends mail to these addresses (no verification-email flow) — a lightweight syntax
# check is all that's actually needed here.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class UserOut(BaseModel):
    id: int
    email: str
    username: str
    full_name: str | None
    role: str
    workspace_id: int
    is_active: bool
    must_reset_password: bool
    created_at: datetime
    last_login_at: datetime | None


class UserCreate(BaseModel):
    email: str
    username: str = Field(min_length=2, max_length=64)
    full_name: str | None = None
    password: str
    role: str = "viewer"

    @field_validator("email")
    @classmethod
    def _valid_email_shape(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError("not a valid email address")
        return v


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
