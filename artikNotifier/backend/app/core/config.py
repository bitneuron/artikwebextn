"""Application settings, loaded from environment / .env (12-factor, no hardcoded secrets)."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    # ── App ───────────────────────────────────────────────────────────────────
    app_name: str = "Artik Notifier"
    environment: str = Field(default="development")  # development | production
    debug: bool = True
    frontend_url: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # ── Security / auth ───────────────────────────────────────────────────────
    secret_key: str = "dev-insecure-change-me-in-production"  # signs JWTs (override in prod)
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    password_reset_expire_minutes: int = 60
    cookie_secure: bool = False          # True in production (HTTPS)
    rate_limit_per_minute: int = 120     # per client IP

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "sqlite:///./artik_notifier.db"

    # ── Email (SMTP) ──────────────────────────────────────────────────────────
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "Artik Notifier <no-reply@artiknotifier.local>"
    smtp_use_tls: bool = True
    # When SMTP is unconfigured, emails are written to the console/log instead of sent.
    email_console_fallback: bool = True

    # ── Scheduler ─────────────────────────────────────────────────────────────
    scheduler_enabled: bool = True
    scheduler_interval_minutes: int = 60   # spec: runs hourly
    notification_max_retries: int = 3

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
