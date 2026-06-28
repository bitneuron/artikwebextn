"""Artik Notifier API — FastAPI application factory + middleware + lifespan."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers import auth, dashboard, health, meta, notifications, reminders
from app.core.config import settings
from app.core.database import init_db
from app.core.logging_config import log_event, setup_logging
from app.scheduler.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging("INFO")
    init_db()
    start_scheduler()
    log_event("app", "startup", environment=settings.environment)
    yield
    stop_scheduler()
    log_event("app", "shutdown")


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan,
              description="Centralized notification & reminder platform for the Artik ecosystem.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── simple in-memory rate limiter (per client IP) ────────────────────────────
_HITS: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def rate_limit_and_headers(request: Request, call_next):
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    window = _HITS[ip]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= settings.rate_limit_per_minute and request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "rate limit exceeded"}, status_code=429)
    window.append(now)

    response = await call_next(request)
    # security headers (XSS / clickjacking / sniffing / CSP)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src *; frame-ancestors 'none'")
    return response


for r in (auth.router, reminders.router, notifications.router, dashboard.router,
          meta.router, health.router):
    app.include_router(r)


@app.get("/")
def root():
    return {"app": settings.app_name, "docs": "/docs", "health": "/api/health"}
