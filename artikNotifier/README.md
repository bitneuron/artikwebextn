# 🔔 Artik Notifier

The centralized **reminder & notification platform** for the Artik ecosystem. Create
recurring and one-time reminders (payments, finance reviews, mortgage, insurance,
taxes, medical, subscriptions, …); a scheduler fires multi-stage notifications over
pluggable channels (email + in-app today, SMS/Push/Slack/Webhook ready).

Part of the **ArtikProjects** monorepo (`artikNotifier/`), alongside `artikBroker`.

> Full requirements: see `../prompts/Artik_Notifier_Requirement_Prompt.md`.

---

## Stack

| Layer | Tech |
|-------|------|
| Frontend | React 18 · TypeScript · Vite · Tailwind CSS · React Router |
| Backend | FastAPI · SQLAlchemy 2 · Pydantic v2 |
| Scheduler | APScheduler (hourly tick → `dispatch_due`) |
| Email | SMTP + Jinja HTML templates (console fallback in dev) |
| Auth | Argon2 password hashing · JWT access/refresh · persisted sessions |
| DB | SQLite (Postgres/RDS-ready via `DATABASE_URL`) |
| Infra | Docker + docker-compose · GitHub Actions CI |

Architecture follows **Clean Architecture**: `routers → services → repositories → models`,
with a **provider plugin registry** for notification channels.

---

## Quick start (local, no Docker)

```bash
# from artikNotifier/
./scripts/dev.sh          # backend :8080 (+ /docs)  ·  frontend :5173
```

Or manually:

```bash
# backend
cd backend && python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080      # → http://localhost:8080/docs

# frontend (new terminal)
cd frontend && npm install && npm run dev       # → http://localhost:5173
```

Open http://localhost:5173, **register**, create a reminder, and (for an instant demo)
hit **POST /api/scheduler/run** to fire due notifications immediately.

In dev, SMTP is unset so reminder emails are **logged to the console** — no mail server
needed. Forgot-password returns a `dev_token` so you can test the reset flow locally.

## Quick start (Docker)

```bash
cp .env.example .env        # set SECRET_KEY (+ SMTP_* for real email)
docker compose up --build   # frontend → http://localhost:8088 · backend → :8080
```

## Tests

```bash
./scripts/test.sh           # backend pytest + frontend build/typecheck
# or: cd backend && . .venv/bin/activate && pytest
```

16 backend tests cover auth, reminder CRUD + lifecycle (snooze/complete/restore/
duplicate/recurring roll-forward), scheduler dispatch, **duplicate prevention**,
channel preferences, bell counts, dashboard, and calendar.

---

## Features

- **Auth** — register / login / logout / refresh / change / forgot / reset (Argon2 + JWT).
- **Reminders** — create / edit / delete / complete / archive / snooze / duplicate /
  restore / search / filter / sort. Categories, priorities, tags, timezone, recurrence
  (one-time → yearly), multi-stage schedule (1mo / 1wk / 2d / same-day / custom).
- **Notifications** — scheduler generates per-channel notifications, deduped & retried;
  in-app + email providers; bell with unread/due/overdue counts; notification center.
- **Dashboard** — upcoming / due-today / overdue / completed / unread + recent activity.
- **Calendar** — month view with per-day reminders.
- **UI** — responsive (desktop/tablet/mobile), light + dark mode.

## Docs

- [Architecture](docs/ARCHITECTURE.md) · [API](docs/API.md) · [ER Diagram](docs/ER_DIAGRAM.md)
- [Setup](docs/SETUP.md) · [Deployment](docs/DEPLOYMENT.md) · [Testing](docs/TESTING.md) · [Roadmap](docs/ROADMAP.md)
