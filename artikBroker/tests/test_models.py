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
