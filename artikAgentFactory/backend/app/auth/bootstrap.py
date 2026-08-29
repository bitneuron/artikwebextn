"""First-admin bootstrap for a brand-new install with zero users. Called once from
main.py's lifespan, after run_migrations() (so a default Workspace already exists)."""
from __future__ import annotations

import os
import secrets as _secrets

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging_config import log_event
from app.core.migrations import backfill_legacy_agents
from app.core.security import hash_password
from app.models.user import User
from app.models.workspace import Workspace


def ensure_initial_admin() -> None:
    db = SessionLocal()
    try:
        if db.query(User).first():
            return  # already bootstrapped

        workspace = db.query(Workspace).filter(Workspace.slug == "default").first()
        if workspace is None:
            workspace = Workspace(name="Default", slug="default")
            db.add(workspace)
            db.flush()

        email = settings.initial_admin_email or os.environ.get("INITIAL_ADMIN_EMAIL", "")
        password = settings.initial_admin_password or os.environ.get("INITIAL_ADMIN_PASSWORD", "")

        if email and password:
            username = settings.initial_admin_username or os.environ.get("INITIAL_ADMIN_USERNAME", "admin")
            admin = User(
                email=email, username=username, full_name="Administrator",
                password_hash=hash_password(password), role="administrator",
                workspace_id=workspace.id, is_active=True, must_reset_password=True,
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)
            log_event("app", "bootstrap admin created from INITIAL_ADMIN_EMAIL", email=email, username=username)
        elif settings.is_production:
            # Fail-closed by construction: the app boots, but nobody can log in until
            # an admin sets INITIAL_ADMIN_EMAIL/PASSWORD and restarts. This is safer
            # than auto-creating a guessable production admin.
            log_event("app", "CRITICAL: no users exist and INITIAL_ADMIN_EMAIL/PASSWORD "
                             "are unset in production — nobody can log in", level=50)
            return
        else:
            dev_password = _secrets.token_urlsafe(15)
            admin = User(
                email="admin@local.test", username="admin", full_name="Local Admin",
                password_hash=hash_password(dev_password), role="administrator",
                workspace_id=workspace.id, is_active=True, must_reset_password=True,
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)
            print(f"\n[artikAgentFactory] Dev admin created — email: admin@local.test  "
                  f"password: {dev_password}\n(must be changed on first login)\n")
            log_event("app", "dev admin bootstrapped")

        backfill_legacy_agents(admin.id, workspace.id)
    finally:
        db.close()
