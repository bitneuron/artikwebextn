# 🔔 Artik Notifier

The centralized **reminder & notification platform** for the Artik ecosystem. Create
recurring and one-time reminders (payments, finance reviews, mortgage, insurance,
taxes, medical, subscriptions, …); a scheduler fires multi-stage notifications over
pluggable channels (email, in-app, and **Slack** today; SMS/Push/Webhook ready).

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

## Data durability on AWS

App Runner has **no persistent disk** — each deploy starts a fresh container. To keep
accounts and reminders across deploys, the production image runs SQLite under
**[Litestream](https://litestream.io)**, which continuously replicates the DB to S3 and
**restores it on every container boot** (`docker-entrypoint.sh`). `deploy.sh` provisions
a versioned, private S3 bucket and an App Runner instance role with scoped S3 access, and
wires `LITESTREAM_BUCKET`/`LITESTREAM_REGION` into the service. Locally (no bucket) the app
just uses an ephemeral SQLite file. For multi-instance scale, switch `DATABASE_URL` to
Postgres/RDS (no code change) and drop the single-instance cap.

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

41 backend tests cover auth, reminder CRUD + lifecycle (snooze/complete/restore/
duplicate/recurring roll-forward), scheduler dispatch, **duplicate prevention**,
channel preferences, bell counts, dashboard, calendar, the AI assistant, security
(IDOR/RBAC/XSS/hashing), and **Quick Notes** (CRUD, search/filter/sort, tags, reminder
conversion, chatbot integration, and per-user isolation).

---

## Features

- **Auth** — register / login / logout / refresh / change / forgot / reset (Argon2 + JWT).
- **Reminders** — create / edit / delete / complete / archive / snooze / duplicate /
  restore / search / filter / sort. Categories, priorities, tags, timezone, recurrence
  (one-time → yearly), multi-stage schedule (1mo / 1wk / 2d / same-day / custom).
- **Quick Notes** — lightweight capture (note text is the only required field) with
  optional title, due date/time, priority, category, and unlimited tags. Full-text
  search (incl. `tag:` / category), filter, sort, status lifecycle
  (active/completed/archived/deleted), and **one-click “Convert to Reminder”** that
  copies the fields and links the reminder back to the preserved note. Mobile floating
  “+” capture. The AI assistant searches notes too.
- **Notifications** — scheduler generates per-channel notifications, deduped & retried;
  in-app, email, and **Slack** providers (set `SLACK_WEBHOOK_URL`; falls back to console
  logging when unset); bell with unread/due/overdue counts; notification center.
- **Dashboard** — upcoming / due-today / overdue / completed / unread + recent activity.
- **Calendar** — month view with per-day reminders.
- **🤖 Ask Artik Assistant** — a chatbot that reviews **your own** reminders,
  notifications, and settings and answers questions ("What's due this week?", "Any
  overdue payments?", "How should I improve my settings?") with safe, read-only
  insights. Strictly scoped to the logged-in user; performs no destructive actions.
- **Admin** — role-based user management (`/admin`), audit-logged, admin-only.
- **UI** — responsive (desktop/tablet/mobile), light + dark mode, per-page browser
  titles (`ArtikNotifier — Dashboard/Calendar/AI Assistant/…`), SEO + Open Graph meta.
- **Artik Platform** — a shared `/platform` landing ("Choose your application") and an
  in-app product switcher to move between Artik apps, plus URL aliases
  (`/artiknotifier`, `/artik-notifier`, `/notifier` → app root). Everything is driven
  by one registry (`frontend/src/platform/apps.ts`): **registering a new Artik app =
  appending a single entry** (name, logo, aliases, url, metadata) — the landing page,
  switcher, and aliases pick it up automatically. SSO-ready (cross-app links are the
  forwarding point for a shared bearer token).

## Security

Per-user auth (Argon2 + JWT access/refresh + revocable sessions), strict
**ownership/IDOR** checks on every reminder/notification/setting/chat endpoint,
**RBAC** for admin features (audit-logged), parameterized queries, CSP + security
headers, rate limiting, env-only secrets, and a production guard that refuses to boot
with a default `SECRET_KEY`. Full review + the automated security test suite are in
[`docs/SECURITY.md`](docs/SECURITY.md).

## Docs

- [Architecture](docs/ARCHITECTURE.md) · [API](docs/API.md) · [ER Diagram](docs/ER_DIAGRAM.md)
- [Setup](docs/SETUP.md) · [Deployment](docs/DEPLOYMENT.md) · [Testing](docs/TESTING.md) · [Roadmap](docs/ROADMAP.md)
