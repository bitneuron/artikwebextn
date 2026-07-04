"""Tests for the LLM model chains + version fallback."""
from __future__ import annotations

import importlib

import models


def test_chains_have_primary_and_fallbacks():
    assert models.CLAUDE and models.GPT
    assert len(models.CLAUDE) >= 2 and len(models.GPT) >= 2       # primary + ≥1 fallback
    assert models.CLAUDE[0].startswith("claude-")
    assert models.GPT[0] == "gpt-5"                               # bumped to most-capable
    # fast tier is distinct/cheaper-first
    assert "haiku" in models.CLAUDE_FAST[0]


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

    assert models.with_fallback(models.CLAUDE, fn) == f"ok:{models.CLAUDE[-1]}"
    assert tried == models.CLAUDE                                 # tried newest → oldest in order


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
