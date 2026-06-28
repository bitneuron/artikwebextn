# Entity-Relationship Diagram

14 tables. SQLite locally; identical schema on Postgres/RDS.

```mermaid
erDiagram
    users ||--o{ sessions : has
    users ||--o{ password_resets : has
    users ||--|| user_preferences : has
    users ||--o{ reminders : owns
    users ||--o{ categories : owns
    users ||--o{ tags : owns
    users ||--o{ notifications : receives
    users ||--o{ audit_logs : acts

    reminders ||--o{ reminder_tags : tagged
    tags ||--o{ reminder_tags : on
    reminders ||--o{ reminder_history : logs
    reminders ||--o{ notification_rules : schedules
    reminders ||--o{ notifications : triggers
    notification_rules ||--o{ notifications : fires
    notifications ||--o{ notification_history : attempts

    users {
        int id PK
        string email UK
        string full_name
        string password_hash
        string role
        bool is_active
        string timezone
        datetime created_at
        datetime last_login_at
    }
    reminders {
        int id PK
        int user_id FK
        string title
        text description
        text notes
        string category
        string priority
        string status
        datetime due_at
        string timezone
        string recurrence
        text schedule
        text channels
        datetime completed_at
        datetime snoozed_until
    }
    notification_rules {
        int id PK
        int reminder_id FK
        int user_id FK
        string offset_key
        datetime fire_at
        text channels
        bool fired
        string dedupe_key UK
    }
    notifications {
        int id PK
        int user_id FK
        int reminder_id FK
        int rule_id FK
        string channel
        string title
        text body
        string status
        bool is_read
        int attempts
        string dedupe_key
    }
```

**Tables:** `users`, `sessions`, `password_resets`, `user_preferences`, `reminders`,
`categories`, `tags`, `reminder_tags`, `reminder_history`, `notification_rules`,
`notifications`, `notification_history`, `email_templates`, `scheduler_jobs`,
`audit_logs`.

Key design points:
- `reminders.schedule` / `reminders.channels` are JSON arrays (text) — portable.
- `notification_rules.dedupe_key` is **unique** → a schedule offset fires once.
- `notifications.dedupe_key` (`<rule>:<channel>`) prevents duplicate deliveries.
- Statuses: reminder = active/completed/archived/snoozed/deleted; notification =
  pending/sent/failed/read/archived/deleted.
