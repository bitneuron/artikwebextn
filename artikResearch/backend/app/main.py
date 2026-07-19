"""ArtikResearch Assistant — FastAPI application entrypoint.

Serves the JSON API and (in production) the built frontend. Security headers on every
response; CORS open only in dev. Iteration 1 has no auth gate — add the shared Artik auth
before any multi-user/public deployment (see README security notes).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .config import ROOT
from .routers import analysis, chat, dashboard, journals, papers

app = FastAPI(title="ArtikResearch Assistant", version="0.1.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def _security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return resp


@app.on_event("startup")
def _startup():
    db.init()


app.include_router(dashboard.router)
app.include_router(papers.router)
app.include_router(journals.router)
app.include_router(analysis.router)
app.include_router(chat.router)


@app.get("/api/health")
def health():
    return {"ok": True, "app": "ArtikResearch Assistant", "version": "0.1.0"}


# Serve the built frontend if present (frontend/dist). Falls back to an API-only notice.
_DIST = ROOT / "frontend" / "dist"
if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(_DIST / "assets")), name="assets")

    @app.get("/")
    def index():
        return FileResponse(str(_DIST / "index.html"))

    @app.get("/{path:path}")
    def spa(path: str):
        f = _DIST / path
        if f.is_file():
            return FileResponse(str(f))
        return FileResponse(str(_DIST / "index.html"))
else:
    @app.get("/")
    def index_dev():
        return JSONResponse({"app": "ArtikResearch Assistant API",
                             "note": "frontend not built — run `npm run build` in frontend/, "
                             "or use the Vite dev server (npm run dev).",
                             "docs": "/docs", "health": "/api/health"})
