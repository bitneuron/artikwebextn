# Setup Guide

## Prerequisites
- Python 3.11+ (3.12 recommended)
- Node 18+ (20 recommended)
- (optional) Docker + Docker Compose

## Backend
```bash
cd artikNotifier/backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env          # optional; sensible defaults work for dev
uvicorn app.main:app --reload --port 8080
```
- API: http://localhost:8080 · Swagger: `/docs`
- The SQLite DB + tables are created automatically on first start.
- The scheduler starts automatically (hourly). For an instant demo call
  `POST /api/scheduler/run`.

## Frontend
```bash
cd artikNotifier/frontend
npm install
npm run dev                       # http://localhost:5173
```
The Vite dev server proxies `/api` → `http://localhost:8080`, so no CORS config is
needed locally. For a separate API origin set `VITE_API_URL` in `frontend/.env`.

## One command
```bash
cd artikNotifier && ./scripts/dev.sh
```

## Email in development
SMTP is unset by default → reminder/reset emails are **logged to the console**
(`EMAIL_CONSOLE_FALLBACK=true`). To send real email, set `SMTP_HOST/PORT/USER/PASSWORD`.

## Environment variables
See [`.env.example`](../.env.example). The important ones:
- `SECRET_KEY` — **set a long random value in production** (signs JWTs).
- `DATABASE_URL` — SQLite by default; Postgres for production.
- `SCHEDULER_INTERVAL_MINUTES` — default 60.
- `SMTP_*` — outbound email.
- `ENVIRONMENT=production` — enables stricter behavior (no dev tokens, secure cookies).
