"""Application settings, loaded from environment / .env (12-factor, no hardcoded secrets)."""
from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    # ── App ───────────────────────────────────────────────────────────────────
    app_name: str = "artikAgentFactory"
    environment: str = "development"  # development | production
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # ── Database ──────────────────────────────────────────────────────────────
    # Local/dev: sqlite via `database_url` directly. AWS: compute_stack.py injects
    # DB_HOST/DB_PORT/DB_NAME as plain env vars plus DB_USERNAME/DB_PASSWORD from the
    # RDS credentials secret — assembled into a postgres `database_url` below rather
    # than requiring infra to build a connection string (keeps the password out of
    # any single composed env var visible in the ECS console).
    database_url: str = "sqlite:///./artik_agent_factory.db"
    db_host: str = ""
    db_port: str = "5432"
    db_name: str = ""
    db_username: str = ""
    db_password: str = ""

    @model_validator(mode="after")
    def _assemble_database_url(self) -> "Settings":
        if self.db_host:
            user = quote_plus(self.db_username)
            pw = quote_plus(self.db_password)
            self.database_url = (
                f"postgresql+psycopg://{user}:{pw}@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        return self

    # ── LLM / research ────────────────────────────────────────────────────────
    anthropic_api_key: str = ""
    web_search_max_uses: int = 5
    max_queries_per_run: int = 4
    extraction_batch_size: int = 15

    # ── Scheduler / background execution ─────────────────────────────────────
    scheduler_enabled: bool = True
    execution_backend: str = "inline"  # inline (local/dev) | sqs (AWS — see scheduler/eventbridge_adapter.py)

    # ── Slack notifications ──────────────────────────────────────────────────
    # A direct Incoming Webhook to this app's own dedicated channel, separate from
    # the shared #artik-notify channel the centralized Artik Notifier posts to (see
    # notify_client.py). SLACK_WEBHOOK_URL comes from core/secrets.py (Secrets
    # Manager in prod, env locally) — never stored here. slack_channel below is
    # display-only (shown in Settings.tsx) — the webhook itself is bound to whichever
    # channel it was created for in Slack, regardless of this value.
    slack_channel: str = "#artik-agent-notify"
    notifications_enabled: bool = True
    notification_timeout_seconds: float = 10.0
    notification_retry_count: int = 3

    # ── Secrets backend ───────────────────────────────────────────────────────
    secrets_backend: str = "env"  # env (local/dev) | aws (Secrets Manager, prod/staging)
    secrets_prefix: str = "artikagentfactory"

    # ── Auth ──────────────────────────────────────────────────────────────────
    session_cookie_name: str = "af_session"
    initial_admin_email: str = ""
    initial_admin_username: str = "admin"
    initial_admin_password: str = ""

    # ── Public URL (used to build links in Slack messages, etc.) ────────────────
    app_base_url: str = ""

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in ("production", "prod")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
