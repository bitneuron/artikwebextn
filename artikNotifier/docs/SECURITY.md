# Security Review & Hardening — Artik Notifier

A full review of authentication, authorization, data access, transport, and frontend
handling. Below: findings, fixes, and the controls now in place. Verified by an
automated security test suite (`tests/test_security.py`).

## Findings & fixes

| # | Severity | Finding | Fix |
|---|----------|---------|-----|
| 1 | High | `POST /api/scheduler/run` (global notification dispatch) was callable by any authenticated user. | Now `require_admin`. |
| 2 | Medium | No admin RBAC was actually enforced anywhere (the `require_admin` dep existed but was unused) — admin features weren't protected. | Added `/api/admin/*` (users list, set-role, deactivate) behind `require_admin`, all **audit-logged**; admin UI hidden from non-admins. |
| 3 | Medium | The app could start in **production** with the insecure default `SECRET_KEY` (used to sign JWTs). | `assert_secure_for_production()` fails startup if `ENVIRONMENT=production` and the default secret is unchanged. |
| 4 | Low | No explicit, tested guarantee that self-registration cannot set a privileged role. | `RegisterIn` has no `role` field; role is derived server-side from `ADMIN_EMAILS` only. Regression test added. |
| 5 | Low | Assistant chatbot is a new data surface — must never cross users. | `AssistantService` is constructed with the authenticated user and **scopes every query to `user_id`**; chat history is per-user. Cross-user test added. |

## Controls in place (verified)

**Authentication & sessions**
- Per-user accounts; **no shared site password**.
- Passwords hashed with **Argon2** (`passlib`), constant-time verify. Never stored,
  returned, or logged in plaintext (`UserOut` excludes `password_hash`).
- **JWT** access (30 min) + refresh (7 day) tokens; refresh sessions persisted and
  revocable → working **logout** and session expiry. Password change/reset revokes
  other sessions.
- Password reset uses a **secure single-use token** with expiry; forgot-password does
  not reveal whether an account exists (no user enumeration).

**Authorization (IDOR / RBAC)**
- Every data endpoint requires a valid bearer token (`get_current_user`).
- All reminder/notification operations resolve through `get_for_user(id, user_id)` /
  `query(user_id)` → a user **can only read/modify their own** reminders, notifications,
  settings, and chat. Cross-user access returns **404** (no existence leak). Even an
  admin cannot read another user's reminder via the data APIs.
- Admin-only endpoints enforce role server-side; the frontend hides admin UI from
  normal users (defense in depth, not the control).

**Injection / XSS / CSRF**
- All DB access is via the SQLAlchemy ORM → **parameterized queries** (SQL injection
  fails safely; malicious IDs hit int path-param validation → 422, never the DB).
- Pydantic validates/﻿bounds all request bodies; integer path params reject injection.
- User content is stored as data and **escaped by React on render** (no
  `dangerouslySetInnerHTML`); email templates use Jinja autoescaping. The assistant
  returns plain text in JSON.
- Auth uses bearer tokens in the `Authorization` header (not cookies) → **no CSRF
  surface** for the API.

**Transport / headers / secrets**
- Security headers on every response: `Content-Security-Policy`, `X-Frame-Options:
  DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`.
- Per-IP **rate limiting** (configurable, default 120/min) on `/api/*` → 429.
- HTTPS is provided by the platform (App Runner); `COOKIE_SECURE=true` in production.
- Secrets come from **environment variables** only; `.env.example` documents them and
  `.env` / `*.db` are git-ignored.

**Auditing**
- Auth events and **admin actions** are written to `audit_logs` + the structured
  `audit` log channel.

## Known trade-offs / future work
- Tokens are kept in `localStorage` (XSS-accessible). Mitigated by strict escaping +
  CSP and no HTML sinks. A future option is HttpOnly+SameSite cookies + CSRF tokens.
- SQLite is single-instance; production should use Postgres/RDS (no code change).
- Optional next steps: account lockout / login backoff, email verification, 2FA,
  per-user encryption of notes at rest.

## Acceptance criteria — status
- ✅ No plaintext password stored anywhere (Argon2; `test_password_is_hashed_and_never_exposed`).
- ✅ Users cannot access another user's reminders/notifications/settings/chat (`test_idor_*`, assistant isolation test).
- ✅ Admin-only features protected (`test_rbac_admin_only`).
- ✅ Reminder/notification APIs validate ownership.
- ✅ XSS attempts handled safely (`test_xss_payload_stored_safely`).
- ✅ SQL-injection attempts fail safely (`test_invalid_ids_safe_errors`).
- ✅ All tests pass (`pytest` → 28 passed).
