"""Vendored trim of artikAgents/agents/shared/model_config.py — kept as a standalone
copy (per the approved plan) so artikAgentFactory has zero import coupling to the
artikAgents submodule's internals, while still reading the SAME shared models.json
and the SAME shared .env for ANTHROPIC_API_KEY (both live one repo over, at fixed
relative paths from this file — see CLAUDE.md's stated repo layout).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# artikAgentFactory/backend/app/services/model_config.py -> parents[4] == ArtikProjects/
# Only true in the local monorepo checkout — the container image (Dockerfile COPYs
# just backend/app to /app/app) has a much shallower tree, so this must degrade to
# None rather than crash at import time. Both _CONFIG_PATH and _ENV_PATH are None-safe
# because _load_config()/get_anthropic_api_key() already catch any exception reading
# them and fall back to _FALLBACK / the ANTHROPIC_API_KEY env var respectively.
try:
    _REPO_ROOT = Path(__file__).resolve().parents[4]
except IndexError:
    _REPO_ROOT = None
_CONFIG_PATH = (_REPO_ROOT / "artikAgents" / "agents" / "shared" / "models.json") if _REPO_ROOT else None
_ENV_PATH = (_REPO_ROOT / "artikAgents" / "agents" / ".env") if _REPO_ROOT else None

_FALLBACK = {
    "anthropic": {"default": "claude-opus-4-8", "synthesis": "claude-opus-4-8", "research": "claude-opus-4-8"},
}

_ENV_OVERRIDES = {
    ("anthropic", "default"): "ANTHROPIC_MODEL",
    ("anthropic", "research"): "ANTHROPIC_RESEARCH_MODEL",
}


def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text())
    except Exception:  # noqa: BLE001 — never let model config crash a run
        return _FALLBACK


_CONFIG = _load_config()


def get_model(provider: str, role: str = "default") -> str:
    env = _ENV_OVERRIDES.get((provider, role))
    if env and os.environ.get(env):
        return os.environ[env]
    prov = _CONFIG.get(provider) or _FALLBACK.get(provider, {})
    return prov.get(role) or prov.get("default") or _FALLBACK["anthropic"]["default"]


def get_anthropic_api_key() -> str:
    """Env var wins; otherwise fall back to the shared .env this repo already uses for
    every Python agent (see CLAUDE.md). Never logged, never returned in API responses."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    try:
        for line in _ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:  # noqa: BLE001
        pass
    return ""
