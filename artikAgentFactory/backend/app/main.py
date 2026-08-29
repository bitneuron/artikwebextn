"""artikAgentFactory API — FastAPI application factory + lifespan.

Independent from ArtikFinance/artikBroker: separate database, separate process, no
shared code beyond a couple of vendored utility modules (see services/model_config.py,
services/notify_client.py)."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routers import (
    agent_access,
    agents,
    alerts,
    audit,
    auth,
    dashboard,
    health,
    notification_settings,
    results,
    runs,
    templates,
    users,
)
from app.auth.bootstrap import ensure_initial_admin
from app.core.config import settings
from app.core.database import init_db
from app.core.logging_config import log_event, setup_logging
from app.core.migrations import run_migrations
from app.core.security_middleware import security_middleware
from app.scheduler.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging("INFO")
    init_db()
    run_migrations()
    ensure_initial_admin()
    start_scheduler()
    log_event("app", "startup", environment=settings.environment)
    yield
    stop_scheduler()
    log_event("app", "shutdown")


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan,
              description="Configurable background research-agent platform. Research that keeps working.")

app.middleware("http")(security_middleware)

# Closed in production — the frontend is same-origin (served via the frontend_dist
# static mount below), so there's no legitimate cross-origin caller. In dev the two
# Vite/uvicorn ports need this to talk to each other.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[] if settings.is_production else settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth.router, users.router, audit.router, agent_access.router, notification_settings.router,
         templates.router, agents.router, runs.router, results.router, alerts.router,
         dashboard.router, health.router):
    app.include_router(r)


_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend_dist"
_HAS_FRONTEND = (_FRONTEND_DIST / "index.html").exists()

if _HAS_FRONTEND and (_FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIST / "assets")), name="assets")


@app.get("/", include_in_schema=False)
def root():
    if _HAS_FRONTEND:
        return FileResponse(str(_FRONTEND_DIST / "index.html"))
    return {"app": settings.app_name, "tagline": "Research that keeps working.",
            "docs": "/docs", "health": "/api/health"}


if _HAS_FRONTEND:
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        if full_path.startswith(("api/", "docs", "redoc", "openapi.json")):
            return JSONResponse({"detail": "not found"}, status_code=404)
        candidate = (_FRONTEND_DIST / full_path).resolve()
        if candidate.is_relative_to(_FRONTEND_DIST.resolve()) and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_FRONTEND_DIST / "index.html"))
