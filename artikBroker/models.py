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
_DEFAULT = {"primary": "openai",
            "tasks": {"extraction": "anthropic", "structured": "anthropic",
                      "reports": "anthropic", "summaries": "anthropic",
                      "questions": "openai"},
            "anthropic": {"default": "claude-opus-5", "synthesis": "claude-opus-5"},
            "openai": {"data": "gpt-6-astra", "chat": "gpt-6-astra", "vision": "gpt-6-astra"}}


def _load() -> dict:
    for p in (os.environ.get("MODELS_JSON"), str(_HERE / "models.json"),
              str(_HERE.parent / "artikAgents/agents/shared/models.json")):
        if p and Path(p).exists():
            try:
                return json.loads(Path(p).read_text())
            except Exception:  # noqa: BLE001
                pass
    return _DEFAULT


_M = _load()
_AN = _M.get("anthropic", {})
_OA = _M.get("openai", {})

# ── Which provider leads ─────────────────────────────────────────────────────
# Every AI feature here can run on either provider. `primary` picks which one is
# tried first; the other stays as the fallback, so a provider outage or an empty
# balance degrades instead of failing. ARTIK_PRIMARY_MODEL overrides the file.
_ALIASES = {"openai": "openai", "astra": "openai", "gpt": "openai", "gpt-6-astra": "openai",
            "anthropic": "anthropic", "claude": "anthropic", "opus": "anthropic",
            "claude-opus-5": "anthropic"}


def _primary(raw) -> str:
    """Canonical provider name. Unrecognised values fall back to openai, never crash."""
    return _ALIASES.get(str(raw or "").strip().lower(), "openai")


PRIMARY = _primary(os.environ.get("ARTIK_PRIMARY_MODEL") or _M.get("primary"))
SECONDARY = "anthropic" if PRIMARY == "openai" else "openai"

# Provider name → the label the API already reports to the UI.
_LABEL = {"anthropic": "claude", "openai": "gpt"}

# ── Per-task policy ──────────────────────────────────────────────────────────
# One model does not win everywhere, so the provider is assigned per workload
# instead. `tasks` in models.json maps a task name to the provider that LEADS it;
# the other provider remains the fallback, so this changes order, never
# availability. A task with no entry falls back to PRIMARY.
#
# ARTIK_PRIMARY_MODEL deliberately does NOT override these: it is the blunt
# instrument for "route everything at one provider" (an outage, a billing stop),
# and letting it silently retarget an accuracy-assigned task would defeat the point.
TASKS = {k: _primary(v) for k, v in (_M.get("tasks") or {}).items()
         if not k.startswith("_") and isinstance(v, str)}


def task_provider(task: str | None) -> str:
    """Which provider leads this task. Unknown or unset → the global primary."""
    return TASKS.get(task or "", PRIMARY)


def task_order(task: str | None) -> tuple[str, str]:
    """(leader, fallback) for a task."""
    lead = task_provider(task)
    return lead, ("anthropic" if lead == "openai" else "openai")


def _dedupe(xs):
    seen, out = set(), []
    for x in xs:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


# ── Capable tier (reasoning: AI search, copilot, single-ticker analysis) ──────
# Explicit environment overrides win; all Claude workloads default to Opus 5.
CLAUDE = _dedupe([
    os.environ.get("ANTHROPIC_MODEL"),
    _AN.get("synthesis"), _AN.get("default"),
    "claude-opus-5",
])
GPT = _dedupe([
    os.environ.get("OPENAI_MODEL"),
    _OA.get("chat"), _OA.get("data"),
    "gpt-6-astra",
])

# ── Bulk routes (names retained; now use the user-selected flagship models) ──
CLAUDE_FAST = _dedupe([
    os.environ.get("ANTHROPIC_FAST_MODEL"),
    "claude-opus-5",
])
GPT_FAST = _dedupe([
    os.environ.get("OPENAI_FAST_MODEL"),
    _OA.get("data"), "gpt-6-astra",
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


def primary_source() -> str:
    """Where the current value came from, so the UI can say why it cannot be changed."""
    return "env" if os.environ.get("ARTIK_PRIMARY_MODEL") else "file"


def _models_json_path() -> Path | None:
    for p in (os.environ.get("MODELS_JSON"), str(_HERE / "models.json"),
              str(_HERE.parent / "artikAgents/agents/shared/models.json")):
        if p and Path(p).exists():
            return Path(p)
    return None


def set_primary(choice: str) -> str:
    """Persist the leading provider to models.json and apply it to this process.

    Raises PermissionError when ARTIK_PRIMARY_MODEL is set, because the env var
    wins on the next read and a saved file would silently not take effect."""
    global PRIMARY, SECONDARY
    if os.environ.get("ARTIK_PRIMARY_MODEL"):
        raise PermissionError(
            "ARTIK_PRIMARY_MODEL is set, so it overrides the file. Unset it to change this here.")
    canon = _primary(choice)
    path = _models_json_path()
    if path is None:
        raise FileNotFoundError("models.json not found; set ARTIK_PRIMARY_MODEL instead")
    data = json.loads(path.read_text())
    data["primary"] = canon
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(tmp, path)
    PRIMARY = canon
    SECONDARY = "anthropic" if canon == "openai" else "openai"
    return canon


def providers(akey: str | None, okey: str | None, task: str | None = None) -> list[tuple[str, str]]:
    """[(label, api_key), ...] in preference order, skipping providers with no key.

    label is the name the API already reports to the UI ("claude" / "gpt").
    `task` selects the per-workload order; omit it for the global primary."""
    keys = {"anthropic": akey, "openai": okey}
    return [(_LABEL[p], keys[p]) for p in task_order(task) if keys[p]]


def cascade(akey: str | None, okey: str | None, claude_fn=None, gpt_fn=None, task: str | None = None):
    """Try each configured provider in preference order; return (result, label, error).

    Runs the primary first and falls back to the other on an exception OR a None
    result, so a provider that returns nothing useful is treated like a failure
    rather than silently yielding an empty answer. Returns (None, None, error)
    when every provider fails; error is the LAST failure, or None if a provider
    simply returned None without raising."""
    fns = {"claude": claude_fn, "gpt": gpt_fn}
    last = None
    for label, key in providers(akey, okey, task):
        fn = fns.get(label)
        if fn is None:
            continue
        try:
            out = fn(key)
        except Exception as e:  # noqa: BLE001
            last = e
            continue
        if out is not None:
            return out, label, None
    return None, None, last


def info() -> dict:
    """Introspection for /api/config etc. (which chains are in effect)."""
    return {"primary": PRIMARY, "secondary": SECONDARY, "tasks": dict(TASKS),
            "task_models": {k: (GPT if v == "openai" else CLAUDE)[0] for k, v in TASKS.items()},
            "primary_label": _LABEL[PRIMARY], "primary_model": (GPT if PRIMARY == "openai" else CLAUDE)[0],
            "claude": CLAUDE, "gpt": GPT, "claude_fast": CLAUDE_FAST, "gpt_fast": GPT_FAST}


# Shared provider compatibility (also copied into the standalone Broker image).
import importlib.util as _import_util
_compat_path = next(p for p in [Path(__file__).with_name("llm_compat.py"), Path(__file__).resolve().parents[1] / "artikAgents/agents/shared/llm_compat.py"] if p.exists())
_compat_spec = _import_util.spec_from_file_location("artik_llm_compat", _compat_path)
_compat = _import_util.module_from_spec(_compat_spec)
_compat_spec.loader.exec_module(_compat)
openai_create = _compat.openai_create
anthropic_create = _compat.anthropic_create
