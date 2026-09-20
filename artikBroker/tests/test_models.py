"""Tests for the LLM model chains + version fallback."""
from __future__ import annotations

import importlib

import models


def test_chains_have_primary_and_fallbacks():
    assert models.CLAUDE and models.GPT
    assert models.CLAUDE == ["claude-opus-5"]
    assert models.GPT == ["gpt-6-astra"]
    # The user selected Opus 5 for every Claude workload, including bulk tasks.
    assert models.CLAUDE_FAST == ["claude-opus-5"]
    assert models.GPT_FAST == ["gpt-6-astra"]


def test_env_override(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-fable-5")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5")
    m = importlib.reload(models)
    assert m.CLAUDE[0] == "claude-fable-5"
    assert m.GPT[0] == "gpt-5"
    # cleanup: reload without the env so other tests see defaults
    monkeypatch.delenv("ANTHROPIC_MODEL"); monkeypatch.delenv("OPENAI_MODEL")
    importlib.reload(models)


def test_with_fallback_uses_previous_when_latest_fails():
    tried = []

    def fn(m):
        tried.append(m)
        if m != models.CLAUDE[-1]:
            raise RuntimeError(f"model unavailable: {m}")
        return f"ok:{m}"

    chain = ["unavailable-primary", models.CLAUDE[-1]]
    assert models.with_fallback(chain, fn) == f"ok:{models.CLAUDE[-1]}"
    assert tried == chain


def test_with_fallback_returns_first_success():
    tried = []
    assert models.with_fallback(models.GPT, lambda m: (tried.append(m), "ok")[1]) == "ok"
    assert tried == [models.GPT[0]]                               # stopped at the primary


def test_with_fallback_raises_if_all_fail():
    def boom(m):
        raise ValueError("nope")
    try:
        models.with_fallback(models.GPT, boom)
        assert False, "expected the last error to propagate"
    except ValueError:
        pass


# ── Primary-provider switch (astra ⇄ claude) ─────────────────────────────────

def test_default_primary_is_astra():
    assert models.PRIMARY == "openai"
    assert models.SECONDARY == "anthropic"
    assert models.info()["primary_label"] == "gpt"
    assert models.info()["primary_model"] == "gpt-6-astra"


def test_primary_aliases_are_accepted():
    for word in ("astra", "openai", "gpt", "GPT-6-Astra"):
        assert models._primary(word) == "openai"
    for word in ("claude", "anthropic", "opus", "Claude-Opus-5"):
        assert models._primary(word) == "anthropic"


def test_unknown_primary_falls_back_to_astra_not_crash():
    assert models._primary("llama") == "openai"
    assert models._primary(None) == "openai"
    assert models._primary("") == "openai"


def test_env_selects_claude_as_primary(monkeypatch):
    monkeypatch.setenv("ARTIK_PRIMARY_MODEL", "claude")
    m = importlib.reload(models)
    assert m.PRIMARY == "anthropic" and m.SECONDARY == "openai"
    assert [lbl for lbl, _ in m.providers("A", "O")] == ["claude", "gpt"]
    monkeypatch.delenv("ARTIK_PRIMARY_MODEL")
    importlib.reload(models)


def test_provider_order_follows_primary_and_skips_missing_keys():
    assert [lbl for lbl, _ in models.providers("A", "O")] == ["gpt", "claude"]
    assert [lbl for lbl, _ in models.providers("A", None)] == ["claude"]
    assert [lbl for lbl, _ in models.providers(None, "O")] == ["gpt"]
    assert models.providers(None, None) == []


def test_cascade_calls_primary_first():
    called = []
    out, label, err = models.cascade("A", "O",
                                     claude_fn=lambda k: called.append("claude") or "c",
                                     gpt_fn=lambda k: called.append("gpt") or "g")
    assert (out, label, err) == ("g", "gpt", None)
    assert called == ["gpt"]                       # claude never ran


def test_cascade_falls_back_when_primary_raises():
    def boom(k):
        raise RuntimeError("astra down")
    out, label, err = models.cascade("A", "O", claude_fn=lambda k: "c", gpt_fn=boom)
    assert (out, label, err) == ("c", "claude", None)


def test_cascade_falls_back_when_primary_returns_none():
    # A provider that yields nothing useful must not shadow the other one.
    out, label, _ = models.cascade("A", "O", claude_fn=lambda k: "c", gpt_fn=lambda k: None)
    assert (out, label) == ("c", "claude")


def test_cascade_reports_last_error_when_all_fail():
    def boom(k):
        raise ValueError("no credit")
    out, label, err = models.cascade("A", "O", claude_fn=boom, gpt_fn=boom)
    assert out is None and label is None and isinstance(err, ValueError)


def test_cascade_skips_provider_without_a_key():
    called = []
    out, label, _ = models.cascade(None, "O",
                                   claude_fn=lambda k: called.append("claude") or "c",
                                   gpt_fn=lambda k: "g")
    assert (out, label) == ("g", "gpt") and called == []


def test_set_primary_refuses_while_env_override_is_set(monkeypatch):
    monkeypatch.setenv("ARTIK_PRIMARY_MODEL", "astra")
    m = importlib.reload(models)
    try:
        m.set_primary("claude")
        assert False, "expected PermissionError: the env var would silently win"
    except PermissionError:
        pass
    monkeypatch.delenv("ARTIK_PRIMARY_MODEL")
    importlib.reload(models)


def test_set_primary_round_trips_through_the_file(tmp_path, monkeypatch):
    cfg = tmp_path / "models.json"
    cfg.write_text('{"primary": "openai", "anthropic": {"default": "claude-opus-5"},'
                   ' "openai": {"data": "gpt-6-astra", "chat": "gpt-6-astra"}}')
    monkeypatch.setenv("MODELS_JSON", str(cfg))
    monkeypatch.delenv("ARTIK_PRIMARY_MODEL", raising=False)
    m = importlib.reload(models)
    assert m.PRIMARY == "openai"
    m.set_primary("claude")
    assert m.PRIMARY == "anthropic"
    import json as _json
    assert _json.loads(cfg.read_text())["primary"] == "anthropic"   # persisted
    assert [lbl for lbl, _ in m.providers("A", "O")] == ["claude", "gpt"]
    m.set_primary("astra")                                          # and back
    assert _json.loads(cfg.read_text())["primary"] == "openai"
    monkeypatch.delenv("MODELS_JSON")
    importlib.reload(models)
