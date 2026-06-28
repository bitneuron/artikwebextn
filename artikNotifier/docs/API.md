# API Reference

Base URL: `/api`. Interactive docs at `/docs` (Swagger) and `/redoc`.
All endpoints except auth + health require `Authorization: Bearer <access_token>`.

## Auth — `/api/auth`
| Method | Path | Body | Notes |
|--------|------|------|-------|
| POST | `/register` | `{email,password,full_name?,timezone?}` | → tokens + user (201) |
| POST | `/login` | `{email,password}` | → `{access_token,refresh_token,user}` |
| POST | `/refresh` | `{refresh_token}` | rotates the refresh token |
| POST | `/logout` | `{refresh_token}` | revokes the session |
| GET | `/me` | — | current user |
| POST | `/change-password` | `{current_password,new_password}` | revokes other sessions |
| POST | `/forgot-password` | `{email}` | emails a reset link (no enumeration); dev returns `dev_token` |
| POST | `/reset-password` | `{token,new_password}` | — |

## Reminders — `/api/reminders`
| Method | Path | Notes |
|--------|------|-------|
| GET | `` | filters: `status,category,priority,search,sort,order,limit,offset` |
| POST | `` | create (see body below) |
| GET | `/{id}` | one reminder |
| PUT | `/{id}` | partial update |
| DELETE | `/{id}` | soft delete |
| POST | `/{id}/complete` | recurring → rolls due_at forward |
| POST | `/{id}/archive` · `/restore` · `/duplicate` | lifecycle |
| POST | `/{id}/snooze` | `{minutes}` or `{until}` |

**Create body:**
```json
{
  "title": "Pay mortgage",
  "description": "...", "notes": "...",
  "category": "Payment", "priority": "high",
  "due_at": "2026-07-01T09:00:00Z", "timezone": "UTC",
  "recurrence": "monthly",
  "schedule": ["1_month","1_week","2_days","on_due"],
  "channels": ["email","in_app"],
  "tags": ["home","money"]
}
```

## Notifications — `/api/notifications`
| Method | Path | Notes |
|--------|------|-------|
| GET | `` | filters: `status,unread_only,search,limit,offset` |
| GET | `/bell` | `{unread_count,due_count,overdue_count,recent[]}` |
| POST | `/{id}/read` · `/read-all` | mark read |
| DELETE | `/{id}` | soft delete |

## Dashboard / Calendar / Meta / System
| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/dashboard` | counts + due_today/overdue/upcoming + recent_activity |
| GET | `/api/calendar?year&month` | month with per-day reminders |
| GET | `/api/categories` · `/tags` · `/options` | form metadata |
| GET/PUT | `/api/preferences` | theme, channels, email/in-app toggles |
| GET | `/api/health` | liveness + db + channels |
| POST | `/api/scheduler/run` | manual dispatch tick (testing/on-demand) |

## Conventions
- Errors: `{ "detail": "message" }` with appropriate HTTP status.
- Auth errors are generic (no user enumeration); rate limit returns **429**.
- Timestamps are ISO-8601 UTC.
