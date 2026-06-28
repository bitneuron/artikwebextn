# Testing Guide

## Run
```bash
cd artikNotifier/backend && . .venv/bin/activate && pytest      # backend
cd artikNotifier/frontend && npm run build                       # frontend typecheck+build
# or everything:
cd artikNotifier && ./scripts/test.sh
```

Tests use an isolated temp SQLite DB (recreated per test) and run with the scheduler
disabled; the dispatch is triggered explicitly via `POST /api/scheduler/run`.

## Coverage (16 backend tests)
| File | Validates |
|------|-----------|
| `test_auth.py` | register, login, `/me`, duplicate email (409), bad creds + **no enumeration**, unauth blocked, refresh rotation, change-password, forgot/reset |
| `test_reminders.py` | CRUD, tags, filter/search/sort, complete/archive/restore/snooze/duplicate, **recurring roll-forward** |
| `test_notifications.py` | dispatch creates per-channel notifications, **dedupe/idempotency**, mark-read/all, delete, **channel preferences** honored |
| `test_dashboard.py` | dashboard counts, calendar, health, options |

## Manual smoke
1. Register at http://localhost:5173.
2. Create a reminder with `due_at` in the past + schedule `["on_due"]`.
3. `POST /api/scheduler/run` → check the bell count + Notification Center.
4. Re-run dispatch → confirm **no duplicates**.
5. Complete a monthly reminder → confirm it rolls to next month and stays active.

## Adding tests
Use the `auth` fixture (registers a user, returns headers) — see `tests/conftest.py`.
Run tests after every change; fix failures before continuing.
