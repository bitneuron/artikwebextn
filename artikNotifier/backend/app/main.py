"""Artik Notifier API — FastAPI application factory + middleware + lifespan."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routers import (admin, assistant, auth, dashboard, health, meta,
                             notifications, notify_api, quick_notes, reminders)
from app.core.config import settings
from app.core.database import init_db
from app.core.logging_config import log_event, setup_logging
from app.scheduler.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging("INFO")
    settings.assert_secure_for_production()   # fail fast on insecure prod config
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


for r in (auth.router, reminders.router, quick_notes.router, notifications.router,
          dashboard.router, meta.router, assistant.router, admin.router,
          notify_api.router, health.router):
    app.include_router(r)


# ── Serve the built frontend (single-image deploy). In dev (no build) the root
# returns API info; in the container, frontend_dist/ holds the Vite build. ───────
_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend_dist"
_HAS_FRONTEND = (_FRONTEND_DIST / "index.html").exists()

if _HAS_FRONTEND and (_FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIST / "assets")), name="assets")


@app.get("/", include_in_schema=False)
def root():
    if _HAS_FRONTEND:
        return FileResponse(str(_FRONTEND_DIST / "index.html"))
    return {"app": settings.app_name, "docs": "/docs", "health": "/api/health"}


if _HAS_FRONTEND:
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # API/docs paths are handled by their routers; everything else is SPA routing.
        if full_path.startswith(("api/", "docs", "redoc", "openapi.json")):
            return JSONResponse({"detail": "not found"}, status_code=404)
        candidate = _FRONTEND_DIST / full_path
        if candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_FRONTEND_DIST / "index.html"))
