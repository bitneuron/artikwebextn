"""The Copilot's per-request model pick, and the snapshot research context.

A pick reorders the chain for ONE call. It must never change the task policy, never
remove the fallback, never forward an id nobody offers, and never let the UI badge
claim a model that did not answer.
"""
from __future__ import annotations

import types

import app
import models


# ── the offered list ─────────────────────────────────────────────────────────

def test_the_three_offered_models_are_the_ones_the_ui_shows():
    assert [m["id"] for m in models.SELECTABLE] == [
        "claude-opus-5", "claude-fable-5-1", "gpt-6-astra"]
    assert [m["provider"] for m in models.SELECTABLE] == ["anthropic", "anthropic", "openai"]


def test_info_exposes_the_list_to_the_picker():
    assert models.info()["selectable"] == models.SELECTABLE


# ── resolving a pick ─────────────────────────────────────────────────────────

def test_ids_and_short_aliases_both_resolve():
    for raw, want in (("claude-opus-5", "claude-opus-5"), ("opus", "claude-opus-5"),
                      ("fable", "claude-fable-5-1"), ("CLAUDE-FABLE-5-1", "claude-fable-5-1"),
                      ("astra", "gpt-6-astra"), ("gpt-6-astra", "gpt-6-astra")):
        assert models.resolve_choice(raw)["id"] == want


def test_auto_blank_and_unknown_all_mean_no_pick():
    # An unknown id must degrade to the normal policy, not reach a provider.
    for raw in ("", None, "auto", "  ", "gpt-9-imaginary", "llama"):
        assert models.resolve_choice(raw) is None


# ── what a pick does to the chain ────────────────────────────────────────────

def test_the_picked_model_leads_and_its_provider_chain_stays_behind_it():
    chain = models.model_chain("fable")
    assert chain[0] == "claude-fable-5-1"
    assert len(chain) > 1 and chain[1:] == [m for m in models.CLAUDE if m != "claude-fable-5-1"]


def test_no_pick_means_no_chain_override():
    assert models.model_chain("auto") is None
    assert models.model_chain(None) is None


def test_a_pick_reorders_providers_but_keeps_the_other_one():
    # 'structured' leads with Claude; picking Astra must put gpt first, claude behind.
    order = [lbl for lbl, _ in models.providers("A", "O", "structured", pin="openai")]
    assert order == ["gpt", "claude"]
    order = [lbl for lbl, _ in models.providers("A", "O", "questions", pin="anthropic")]
    assert order == ["claude", "gpt"]


def test_an_unrecognised_pin_falls_back_to_the_task_policy():
    assert [lbl for lbl, _ in models.providers("A", "O", "structured", pin="nonsense")] == \
           [lbl for lbl, _ in models.providers("A", "O", "structured")]


def test_a_pick_does_not_rewrite_the_task_policy():
    before = dict(models.TASKS)
    models.resolve_choice("fable")
    models.model_chain("astra")
    assert models.TASKS == before
    assert models.task_provider("structured") == "anthropic"


# ── which model actually answered ────────────────────────────────────────────

def test_call_model_reports_the_model_that_succeeded():
    out, used = models.call_model(["a", "b", "c"], lambda m: m.upper() if m == "b" else 1 / 0)
    assert (out, used) == ("B", "b")


def test_call_model_reraises_when_the_whole_chain_fails():
    try:
        models.call_model(["a", "b"], lambda m: 1 / 0)
    except ZeroDivisionError:
        pass
    else:
        raise AssertionError("a fully failed chain must raise")


def test_with_fallback_still_returns_just_the_result():
    assert models.with_fallback(["a"], lambda m: m) == "a"


# ── the snapshot research context ────────────────────────────────────────────

def _req(user):
    r = types.SimpleNamespace()
    r.state = types.SimpleNamespace(user=user)
    return r


def test_snapshot_context_is_labelled_as_point_in_time():
    block = app._copilot_context_block("snapshot", {"page_type": "snapshot", "stocks": []})
    assert "SELECTED PORTFOLIO SNAPSHOT" in block
    assert "re-scored live" in block          # the model must not treat prices as stale
    assert "source of truth" in block


def test_snapshot_context_carries_the_engine_rows():
    ctx = {"page_type": "snapshot", "stocks": [{"ticker": "AAPL", "artik_score": 78}]}
    assert '"AAPL"' in app._copilot_context_block("snapshot", ctx)


def test_snapshot_context_is_admin_only(monkeypatch):
    # Portfolio data is admin-only at /api/portfolio; the Copilot must match it, or a
    # non-admin could research a snapshot simply by posting one to /api/copilot.
    monkeypatch.setattr(app, "OPEN_MODE", False)
    monkeypatch.setattr(app, "_current_user", lambda r: {"id": 2, "role": "user"})
    assert app._is_admin(_req(None)) is False
    monkeypatch.setattr(app, "_current_user", lambda r: {"id": 1, "role": "admin"})
    assert app._is_admin(_req(None)) is True


# ── a model that refuses forced tool use (Fable) ─────────────────────────────

class _Boom(Exception):
    pass


def test_only_the_tool_choice_400_triggers_the_plain_text_retry():
    assert app._forced_tools_unsupported(
        Exception('tool_choice: type "tool" and "any" are not supported for this model.')) is True
    assert app._forced_tools_unsupported(Exception("overloaded_error")) is False
    assert app._forced_tools_unsupported(Exception("tool_choice was odd")) is False


def test_fable_answers_in_plain_text_and_keeps_the_reply_shape(monkeypatch):
    calls = []

    def fake_create(_client, **kw):
        calls.append(kw)
        if kw.get("tool_choice"):
            raise _Boom('tool_choice: type "tool" and "any" are not supported for this model.')
        return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text="NVDA leads.")])

    monkeypatch.setattr(app._models, "anthropic_create", fake_create)
    monkeypatch.setitem(__import__("sys").modules, "anthropic",
                        types.SimpleNamespace(Anthropic=lambda api_key=None: object()))
    used = {}
    out = app._copilot_anthropic([{"role": "user", "content": "hi"}], "SYS", "key",
                                 chain=["claude-fable-5-1"], used=used)
    assert out["answer"] == "NVDA leads."
    assert out["needs_clarification"] is False
    assert out["mode"] == ""            # the endpoint supplies the default, nothing is claimed
    assert used["model"] == "claude-fable-5-1"
    # The retry keeps the same system prompt plus the plain-text instruction, and no tools.
    assert "tools" not in calls[1] and calls[1]["system"].startswith("SYS")
    assert "source of truth" in calls[1]["system"]


def test_a_real_provider_error_still_falls_down_the_chain(monkeypatch):
    seen = []

    def fake_create(_client, **kw):
        seen.append(kw["model"])
        if kw["model"] == "claude-fable-5-1":
            raise _Boom("overloaded_error")
        return types.SimpleNamespace(content=[types.SimpleNamespace(
            type="tool_use", input={"answer": "ok", "mode": "analysis"})])

    monkeypatch.setattr(app._models, "anthropic_create", fake_create)
    monkeypatch.setitem(__import__("sys").modules, "anthropic",
                        types.SimpleNamespace(Anthropic=lambda api_key=None: object()))
    used = {}
    out = app._copilot_anthropic([{"role": "user", "content": "hi"}], "SYS", "key",
                                 chain=["claude-fable-5-1", "claude-opus-5"], used=used)
    assert out["answer"] == "ok"
    assert seen == ["claude-fable-5-1", "claude-opus-5"]
    assert used["model"] == "claude-opus-5"   # the badge must name the model that answered


# ── oversized contexts ───────────────────────────────────────────────────────

def _rows(n, value=True):
    return [{"ticker": f"T{i:03d}", "artik_score": 50 + (i % 40), "sector": "Technology",
             "note": "x" * 300, **({"market_value": float(i)} if value else {})}
            for i in range(n)]


def test_a_context_that_fits_is_untouched():
    ctx = {"page_type": "snapshot", "stocks": _rows(3)}
    blob, note = app._fit_context(ctx)
    assert note == "" and blob == __import__("json").dumps(ctx, default=str)


def test_an_oversized_context_keeps_whole_rows_and_stays_valid_json():
    import json
    ctx = {"page_type": "snapshot", "page_summary": {"holdings": 400}, "stocks": _rows(400)}
    blob, note = app._fit_context(ctx)
    kept = json.loads(blob)                      # never a half-written row
    assert 0 < len(kept["stocks"]) < 400
    assert len(blob) <= app._CTX_BUDGET
    assert all(set(r) == set(ctx["stocks"][0]) for r in kept["stocks"])


def test_the_omission_is_stated_not_hidden():
    ctx = {"page_type": "snapshot", "stocks": _rows(400)}
    _blob, note = app._fit_context(ctx)
    assert "omitted to fit" in note and "not describe the list as complete" in note


def test_the_biggest_positions_are_the_ones_kept():
    import json
    ctx = {"page_type": "snapshot", "stocks": _rows(400)}
    blob, note = app._fit_context(ctx)
    kept = [r["market_value"] for r in json.loads(blob)["stocks"]]
    assert kept == sorted(kept, reverse=True)
    assert min(kept) > 0 and max(kept) == 399.0      # the largest holding is never dropped
    assert "largest by market value" in note


def test_rows_without_values_keep_page_order():
    import json
    ctx = {"page_type": "page", "stocks": _rows(400, value=False)}
    blob, note = app._fit_context(ctx)
    kept = [r["ticker"] for r in json.loads(blob)["stocks"]]
    assert kept == sorted(kept) and kept[0] == "T000"
    assert "first in page order" in note
