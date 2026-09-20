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
                      "reports": "openai", "summaries": "openai", "questions": "openai"},
            "anthropic": {"default": "claude-opus-5", "synthesis": "claude-opus-5",
                          "fallback": "claude-opus-4-8", "fast": "claude-haiku-4-5-20251001",
                          "fast_fallback": "claude-haiku-4-5-20251001"},
            "openai": {"data": "gpt-6-astra", "chat": "gpt-6-astra", "vision": "gpt-6-astra",
                       "fallback": "gpt-5", "fast": "gpt-6-astra", "fast_fallback": "gpt-5-mini"},
            "selectable": [{"id": "claude-opus-5", "label": "Claude Opus 5", "provider": "anthropic"},
                           {"id": "claude-fable-5-1", "label": "Fable 5.1", "provider": "anthropic"},
                           {"id": "gpt-6-astra", "label": "GPT Astra", "provider": "openai"}]}


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
    _AN.get("fallback"),          # previous version, tried only if the flagship errors
])
GPT = _dedupe([
    os.environ.get("OPENAI_MODEL"),
    _OA.get("chat"), _OA.get("data"),
    "gpt-6-astra",
    _OA.get("fallback"),
])

# ── Bulk routes ──────────────────────────────────────────────────────────────
# Short, bounded, low-stakes work that can run many times per request. A flagship
# here is pure cost: these chains lead with the small model and keep the flagship
# behind it, so quality still degrades gracefully rather than failing.
CLAUDE_FAST = _dedupe([
    os.environ.get("ANTHROPIC_FAST_MODEL"),
    _AN.get("fast"),
    _AN.get("fast_fallback"),
    _AN.get("default"), "claude-opus-5",
])
GPT_FAST = _dedupe([
    os.environ.get("OPENAI_FAST_MODEL"),
    _OA.get("fast"),
    _OA.get("fast_fallback"),
    _OA.get("data"), "gpt-6-astra",
])


# ── User-picked model (one request) ──────────────────────────────────────────
# The Copilot lets the user pin a single model for a single question. That is a
# different question from `tasks`, which sets the default for a whole workload:
# a pin reorders the providers and puts the picked model at the head of its
# chain, while the rest of that chain — and then the other provider — stay behind
# it, so a pin changes what leads, never whether an answer comes back. The reply
# reports the model that ACTUALLY ran, so the UI badge is never a guess.
SELECTABLE = [
    {"id": str(m.get("id")), "label": str(m.get("label") or m.get("id")),
     "provider": _primary(m.get("provider"))}
    for m in (_M.get("selectable") or _DEFAULT["selectable"])
    if isinstance(m, dict) and m.get("id")
]

_CHOICE_ALIASES = {"opus": "claude-opus-5", "claude": "claude-opus-5",
                   "fable": "claude-fable-5-1",
                   "astra": "gpt-6-astra", "gpt": "gpt-6-astra", "openai": "gpt-6-astra"}


def resolve_choice(raw) -> dict | None:
    """The selectable model the user picked, or None for auto/blank/unknown.

    An unrecognised id resolves to None instead of being forwarded: a bad pin must
    degrade to the normal per-task policy, never send a made-up model name."""
    key = str(raw or "").strip().lower()
    if not key or key == "auto":
        return None
    key = _CHOICE_ALIASES.get(key, key)
    return next((m for m in SELECTABLE if m["id"].lower() == key), None)


def model_chain(choice) -> list[str] | None:
    """Picked model first, then its provider's usual chain as version fallback."""
    pick = choice if isinstance(choice, dict) else resolve_choice(choice)
    if not pick:
        return None
    base = CLAUDE if pick["provider"] == "anthropic" else GPT
    return _dedupe([pick["id"]] + list(base))


def call_model(models: list[str], fn):
    """Call fn(model) down the chain until one succeeds → (result, model used).

    Falls back to the previous version if the latest errors; re-raises the last
    error only if every model in the chain fails."""
    last = None
    for m in models:
        try:
            return fn(m), m
        except Exception as e:  # noqa: BLE001
            last = e
    if last:
        raise last
    raise RuntimeError("no model configured")


def with_fallback(models: list[str], fn):
    """call_model for callers that do not need to know which model answered."""
    return call_model(models, fn)[0]


def primary_source() -> str:
    """Where the current value came from, so the UI can say why it cannot be changed."""
    return "env" if os.environ.get("ARTIK_PRIMARY_MODEL") else "file"


def _models_json_path() -> Path | None:
    for p in (os.environ.get("MODELS_JSON"), str(_HERE / "models.json"),
              str(_HERE.parent / "artikAgents/agents/shared/models.json")):
        if p and Path(p).exists():
            return Path(p)
    return None


def apply_primary(choice: str) -> str:
    """Set the leading provider for THIS process only. No file is written.

    Used to re-apply a setting persisted elsewhere (the Litestream-backed DB), which
    is the only storage that survives a redeploy on App Runner.
    """
    global PRIMARY, SECONDARY
    canon = _primary(choice)
    PRIMARY, SECONDARY = canon, ("anthropic" if canon == "openai" else "openai")
    return canon


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


def providers(akey: str | None, okey: str | None, task: str | None = None,
              pin: str | None = None) -> list[tuple[str, str]]:
    """[(label, api_key), ...] in preference order, skipping providers with no key.

    label is the name the API already reports to the UI ("claude" / "gpt").
    `task` selects the per-workload order; omit it for the global primary.
    `pin` is a provider a user explicitly picked for this one call and leads when
    given — an unrecognised value is ignored rather than guessed at, so a typo
    falls back to the task policy instead of silently retargeting it."""
    keys = {"anthropic": akey, "openai": okey}
    order = ((pin, "anthropic" if pin == "openai" else "openai")
             if pin in ("anthropic", "openai") else task_order(task))
    return [(_LABEL[p], keys[p]) for p in order if keys[p]]


def cascade(akey: str | None, okey: str | None, claude_fn=None, gpt_fn=None, task: str | None = None,
            pin: str | None = None):
    """Try each configured provider in preference order; return (result, label, error).

    Runs the primary first and falls back to the other on an exception OR a None
    result, so a provider that returns nothing useful is treated like a failure
    rather than silently yielding an empty answer. Returns (None, None, error)
    when every provider fails; error is the LAST failure, or None if a provider
    simply returned None without raising."""
    fns = {"claude": claude_fn, "gpt": gpt_fn}
    last = None
    for label, key in providers(akey, okey, task, pin):
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
            "selectable": [dict(m) for m in SELECTABLE],
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
