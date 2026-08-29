"""Single write path into run_logs. Every message is scrubbed of anything that looks
like a secret BEFORE insert — no call site can bypass this, which is what makes the
"logs must never expose secrets" guarantee actually hold."""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models.run_log import RunLog

_SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9\-_]{6,}"),
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-_.]{10,}"),
    re.compile(r"(?i)(x-api-key|api[_-]?key)['\"]?\s*[:=]\s*['\"]?[^\s'\"]+"),
]


def _scrub(text: str) -> str:
    out = text
    for pat in _SECRET_PATTERNS:
        out = pat.sub("[redacted]", out)
    return out


def log_run(db: Session, run_id: int, stage: str, message: str, level: str = "info") -> None:
    db.add(RunLog(run_id=run_id, stage=stage, level=level, message=_scrub(str(message))[:4000]))
    db.flush()
