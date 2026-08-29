"""Role-level (platform) permissions — the part of the RBAC model that is NOT
resolved per-agent (see access.py for that). A global role gates exactly two kinds
of thing: admin-exclusive platform actions, and who may create agents at all. Every
other capability on a specific agent flows from agent_access grants, independent of
global role (see the approved plan §1 for the full reasoning)."""
from __future__ import annotations

ROLES = ("administrator", "agent_manager", "researcher", "viewer")

CAN_CREATE_AGENTS = {"administrator", "agent_manager"}

# Platform-level actions no per-agent grant can ever substitute for.
ADMIN_ONLY_ACTIONS = {
    "user.manage",
    "audit.view",
    "notification_settings.manage",
    "secrets.view_status",
}
