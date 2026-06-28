# Future Roadmap

Artik Notifier is designed to extend without rewriting the core. The notification
engine, scheduling, and delivery are exposed through clean service interfaces + REST
APIs so other Artik apps integrate via events/HTTP.

## Notification channels (plugin)
Already pluggable via `NotificationProvider` + `registry`. Planned providers:
- SMS (Twilio/SNS) · Push (FCM/APNs/Web Push) · Slack · Teams · Discord · WhatsApp
- Generic **Webhook** + outbound REST integrations

Each is a new provider class + `register(...)` — no engine change.

## Platform integrations
- **Artik Broker alerts** — financial / stock / portfolio reminders auto-created via the
  REST API (e.g. "earnings in 3 days", "rebalance due").
- **AI-generated reminders** — natural-language → reminder (LLM endpoint).
- **Gmail / Google Calendar / Outlook** sync (two-way).
- Family sharing · organization reminders · **RBAC** (admin role already modeled).
- Mobile apps (the API + responsive PWA are ready) · voice reminders.

## Infrastructure
- EventBridge → Lambda scheduler · SES email · SNS/SQS fan-out · RDS Postgres / DynamoDB.
- Per-user digest emails (`digest_enabled` already in preferences).
- Quiet hours / per-channel routing rules · localization / i18n.

## Eventing
Emit domain events (`reminder.created`, `notification.sent`, …) to an internal bus
(SNS/EventBridge) so future Artik services can subscribe without coupling to the DB.
