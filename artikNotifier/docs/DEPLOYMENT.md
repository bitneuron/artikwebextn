# Deployment Guide

## Docker Compose (single host)
```bash
cd artikNotifier
cp .env.example .env      # set a strong SECRET_KEY (+ SMTP_* for real email)
docker compose up --build -d
```
- Frontend (nginx) → http://localhost:8088 (proxies `/api` → backend)
- Backend (uvicorn) → http://localhost:8080
- SQLite persists in the `notifier_data` volume.

Set in `.env` for production:
```
ENVIRONMENT=production
SECRET_KEY=<64+ random chars>
FRONTEND_URL=https://notifier.yourdomain.com
CORS_ORIGINS=https://notifier.yourdomain.com
SMTP_HOST=...  SMTP_USER=...  SMTP_PASSWORD=...
```

## Production hardening
- Terminate **TLS** at a reverse proxy / load balancer; set `COOKIE_SECURE=true`.
- Use a managed DB: `DATABASE_URL=postgresql+psycopg://…` (RDS). No code change.
- Run the scheduler in **one** instance only (or set `SCHEDULER_ENABLED=false` on web
  replicas and run a dedicated scheduler/worker, or move to EventBridge → Lambda).
- Rotate `SECRET_KEY` via your secrets manager; never bake into images.

## AWS-ready path
| Local | AWS |
|-------|-----|
| APScheduler hourly tick | **EventBridge** rule → **Lambda** calling `dispatch_due` |
| SMTP email provider | **SES** (an Email provider variant) |
| Fan-out / async delivery | **SNS / SQS** |
| SQLite | **RDS Postgres** (or DynamoDB via a new repository impl) |
| Container | ECS/Fargate or App Runner (backend), S3+CloudFront (frontend `dist`) |

The work unit (`services.notification_service.dispatch_due`) is framework-agnostic, so
the Lambda handler is a thin wrapper around it.

## CI
GitHub Actions (`/.github/workflows/artik-notifier-ci.yml`) runs backend `pytest`
and the frontend `build` on every push/PR touching `artikNotifier/**`.
