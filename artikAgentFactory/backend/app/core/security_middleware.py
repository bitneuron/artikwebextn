"""Security headers, CSP, request-id, rate limiting, and request-size limits — ported
from artikBroker's `_security_headers`/`_auth_gate` pattern (app.py:224-289) and
tightened for this app's compiled Vite/React bundle (no inline scripts needed, unlike
artikBroker's inline-script HTML UI)."""
from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque

from fastapi import Request
from starlette.responses import JSONResponse

from app.core.config import settings

MAX_REQUEST_BODY_BYTES = 1_000_000  # ~1MB — plenty for this app's JSON API, blocks trivial resource-exhaustion POSTs

_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "  # Tailwind's runtime-injected utility styles
    "img-src 'self' data:; "
    "font-src 'self' data:; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "connect-src 'self'"
)

# IP-keyed sliding-window limiter — a coarser, second net on top of the
# identity-keyed login throttle (core/login_throttle.py).
_GENERAL_WINDOW_SECONDS = 60
_GENERAL_MAX_REQUESTS = 300
_LOGIN_WINDOW_SECONDS = 60
_LOGIN_MAX_REQUESTS = 20

_general_hits: dict[str, deque] = defaultdict(deque)
_login_hits: dict[str, deque] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_limited(bucket: dict[str, deque], key: str, window: int, limit: int) -> bool:
    now = time.time()
    hits = bucket[key]
    while hits and now - hits[0] > window:
        hits.popleft()
    if len(hits) >= limit:
        return True
    hits.append(now)
    return False


async def security_middleware(request: Request, call_next):
    request.state.request_id = request.headers.get("x-request-id") or uuid.uuid4().hex

    if request.url.path.startswith("/api/"):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_REQUEST_BODY_BYTES:
            return JSONResponse({"detail": "request body too large"}, status_code=413)

        ip = _client_ip(request)
        is_login = request.url.path == "/api/auth/login"
        limited = (_rate_limited(_login_hits, ip, _LOGIN_WINDOW_SECONDS, _LOGIN_MAX_REQUESTS) if is_login
                  else _rate_limited(_general_hits, ip, _GENERAL_WINDOW_SECONDS, _GENERAL_MAX_REQUESTS))
        if limited:
            return JSONResponse({"detail": "rate limit exceeded"}, status_code=429)

    response = await call_next(request)

    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Content-Security-Policy"] = _CSP
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response
