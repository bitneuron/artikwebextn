"""Security-relevant action log — distinct from RunLog (pipeline diagnostics).
`record_audit()` is the ONLY write path into `audit_events`, and it defensively
strips anything that looks like a secret from metadata before it's ever persisted
(mirrors the discipline already established in pipeline/log_scrub.py)."""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.utils import to_json
from app.models.audit_event import AuditEvent
from app.models.user import User

_FORBIDDEN_METADATA_KEYS = {"password", "token", "secret", "cookie", "session", "api_key", "apikey"}


def _safe_metadata(metadata: dict | None) -> dict:
    if not metadata:
        return {}
    return {k: v for k, v in metadata.items() if not any(bad in k.lower() for bad in _FORBIDDEN_METADATA_KEYS)}


def _client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else None


def record_audit(
    db: Session, *, actor: User | None, action: str, resource_type: str,
    resource_id: str | int | None = None, outcome: str = "success",
    request: Request | None = None, metadata: dict | None = None,
) -> None:
    actor_label = f"user:{actor.id} {actor.email}" if actor else "system:scheduler"
    request_id = getattr(request.state, "request_id", None) if request is not None else None
    db.add(AuditEvent(
        actor_user_id=actor.id if actor else None,
        actor_label=actor_label,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        outcome=outcome,
        request_id=request_id,
        ip_address=_client_ip(request),
        metadata_json=to_json(_safe_metadata(metadata)),
    ))
