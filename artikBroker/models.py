"""LLM model selection for artikBroker — single source of truth + version fallback.

Reads the shared `models.json` (baked into the image, or MODELS_JSON path) so a version
bump there propagates here too, with env overrides (ANTHROPIC_MODEL / OPENAI_MODEL /
ANTHROPIC_FAST_MODEL / OPENAI_FAST_MODEL) taking precedence.

Each provider exposes an ORDERED chain (newest/most-capable → previous versions). Call
LLMs via `with_fallback(chain, fn)`: if the latest model errors (unavailable, transient,
etc.) it automatically falls back to the previous version.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_DEFAULT = {"anthropic": {"default": "claude-opus-4-8", "synthesis": "claude-opus-4-8"},
            "openai": {"data": "gpt-5-mini", "chat": "gpt-5-mini", "vision": "gpt-5"}}


def _load() -> dict:
    for p in (os.environ.get("MODELS_JSON"), str(_HERE / "models.json")):
        if p and Path(p).exists():
            try:
                return json.loads(Path(p).read_text())
            except Exception:  # noqa: BLE001
                pass
    return _DEFAULT


_M = _load()
_AN = _M.get("anthropic", {})
_OA = _M.get("openai", {})


def _dedupe(xs):
    seen, out = set(), []
    for x in xs:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


# ── Capable tier (reasoning: AI search, copilot, single-ticker analysis) ──────
# Newest/most-capable first, then previous versions as automatic fallbacks.
CLAUDE = _dedupe([
    os.environ.get("ANTHROPIC_MODEL"),
    _AN.get("synthesis"), _AN.get("default"),
    "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-4-6",
])
GPT = _dedupe([
    os.environ.get("OPENAI_MODEL"),
    "gpt-5",                                   # bump: most-capable GPT-5 first
    _OA.get("chat"), _OA.get("data"),
    "gpt-5-mini",
])

# ── Fast tier (bulk / high-volume: the rate-limit analysis fallback) ──────────
CLAUDE_FAST = _dedupe([
    os.environ.get("ANTHROPIC_FAST_MODEL"),
    "claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-opus-4-8",
])
GPT_FAST = _dedupe([
    os.environ.get("OPENAI_FAST_MODEL"),
    _OA.get("data"), "gpt-5-mini",
])


def with_fallback(models: list[str], fn):
    """Call fn(model) for each model in order until one succeeds.

    Falls back to the previous version if the latest errors; re-raises the last
    error only if every model in the chain fails."""
    last = None
    for m in models:
        try:
            return fn(m)
        except Exception as e:  # noqa: BLE001
            last = e
    if last:
        raise last
    raise RuntimeError("no model configured")


def info() -> dict:
    """Introspection for /api/config etc. (which chains are in effect)."""
    return {"claude": CLAUDE, "gpt": GPT, "claude_fast": CLAUDE_FAST, "gpt_fast": GPT_FAST}
