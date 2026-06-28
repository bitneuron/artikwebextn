# Architecture

Artik Notifier is an **event-driven notification platform** built with Clean
Architecture and a Repository + Service layering, so business logic is isolated from
both the web framework and the data store.

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (React/TS/Vite/Tailwind)                              │
│  pages → api/client (fetch + auto refresh) → REST /api/*        │
└───────────────────────────────┬─────────────────────────────────┘
                                 │ JSON over HTTP (JWT bearer)
┌───────────────────────────────▼─────────────────────────────────┐
│  FastAPI app (app/main.py)                                      │
│   middleware: CORS · rate-limit · security headers (CSP/XSS)    │
│   routers (app/api/routers/*)  ── thin HTTP layer               │
│        ↓                                                         │
│   services (app/services/*)    ── business logic / use-cases    │
│        ↓                                                         │
│   repositories (app/repositories/*) ── data access (ORM)        │
│        ↓                                                         │
│   models (SQLAlchemy) → SQLite / Postgres                       │
│                                                                 │
│   notifications/ registry ── pluggable channel providers        │
│   scheduler/ (APScheduler) ── hourly → services.dispatch_due    │
└─────────────────────────────────────────────────────────────────┘
```

## Layers

- **Routers** (`app/api/routers`): validate input (Pydantic), call a service, map
  domain errors → HTTP. No business logic.
- **Services** (`app/services`): the use-cases — auth, reminders (+ rule rebuild),
  the notification engine (`dispatch_due`), dashboard, calendar, email.
- **Repositories** (`app/repositories`): typed CRUD/queries per aggregate. The only
  code that touches the session. Swappable for another store.
- **Models** (`app/models`): SQLAlchemy 2.0 typed models = the 16 tables (incl.
  `quick_notes` + `quick_note_tags` for the Quick Notes module).

## Notification flow (the core)

1. Creating/editing a reminder calls `ReminderService.rebuild_rules`, which expands
   the reminder's **schedule offsets** (`1_month`, `1_week`, … `on_due`) into
   `notification_rules` rows, each with a `fire_at` time and a **`dedupe_key`**.
2. The **scheduler** runs `dispatch_due` every hour (APScheduler; configurable). It
   loads rules with `fire_at <= now AND fired = false`, and for each requested channel
   creates a `notification` (deduped by `<rule>:<channel>`), then delivers it via the
   channel's **provider** (`notifications/registry`).
3. Delivery results are recorded in `notification_history`; transient failures retry
   up to `NOTIFICATION_MAX_RETRIES`. Each tick is logged as a `scheduler_jobs` row.
4. Completing a **recurring** reminder rolls `due_at` forward and rebuilds its rules.

This makes the platform **idempotent** (no duplicate notifications) and **extensible**
(new channels = new provider, no engine change).

## Plugin architecture

`NotificationProvider` (ABC) defines `send(title, body, context) -> (ok, detail)`.
`notifications/registry.py` registers providers by channel name. Built-ins: `in_app`,
`email`. Adding SMS/Push/Slack/Webhook = implement a provider + `register(...)`. The
scheduler and notification engine never change.

## Assistant (chatbot) data flow

`POST /api/assistant/chat` → `get_current_user` (JWT) → `AssistantService(db, user)`.
The service is **constructed with the authenticated user** and every query inside it is
filtered by `self.user_id`, so it can only ever read that user's reminders,
notifications, and preferences. It is deterministic (intent routing + insight rules —
no external LLM, no raw SQL exposed) and **read-only** (no edits/deletes). Each turn is
persisted to `chat_messages` (per-user) so history is private and resumable.
`GET /api/assistant/insights` returns proactive suggestions over the same scoped data.

## Security data flow (defense in depth)

```
request → rate-limit + security-header middleware
        → router (Pydantic validates body; int path params reject injection)
        → get_current_user (JWT) / require_admin (role from DB)
        → service → repository.get_for_user(id, user_id)   ← ownership/IDOR gate
        → ORM (parameterized) → DB
response ← Pydantic response_model (UserOut never includes password_hash)
        ← React escapes on render (no HTML sinks) ; emails Jinja-autoescaped
```
Admin actions additionally write an `audit_logs` row. See `docs/SECURITY.md`.

## Future AWS mapping

`dispatch_due(db)` is the unit of work — the same function a **Lambda** handler calls.
Swap APScheduler for **EventBridge → Lambda**; SES for SMTP (an Email provider variant);
SNS/SQS for fan-out. `DATABASE_URL` moves SQLite → **RDS Postgres** with no code change.
