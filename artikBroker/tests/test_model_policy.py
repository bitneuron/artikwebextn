"""Per-task model policy and the financial-extraction cross-check."""
from __future__ import annotations

import importlib

import app
import models


# ── policy ───────────────────────────────────────────────────────────────────

def test_accuracy_policy_assignments():
    assert models.task_provider("extraction") == "anthropic"
    assert models.task_provider("structured") == "anthropic"
    assert models.task_provider("reports") == "anthropic"
    assert models.task_provider("summaries") == "anthropic"
    assert models.task_provider("questions") == "openai"


def test_unknown_task_uses_the_global_primary():
    assert models.task_provider("no-such-task") == models.PRIMARY
    assert models.task_provider(None) == models.PRIMARY


def test_task_changes_order_but_never_drops_the_fallback():
    for task in ("extraction", "questions"):
        order = [lbl for lbl, _ in models.providers("A", "O", task)]
        assert len(order) == 2 and set(order) == {"claude", "gpt"}
    assert [l for l, _ in models.providers("A", "O", "extraction")][0] == "claude"
    assert [l for l, _ in models.providers("A", "O", "questions")][0] == "gpt"


def test_cascade_honours_the_task_over_the_primary():
    called = []
    out, label, _ = models.cascade("A", "O",
                                   claude_fn=lambda k: called.append("claude") or "c",
                                   gpt_fn=lambda k: called.append("gpt") or "g",
                                   task="extraction")
    assert (out, label) == ("c", "claude") and called == ["claude"]


def test_env_override_does_not_silently_retarget_an_assigned_task(monkeypatch):
    # ARTIK_PRIMARY_MODEL is the blunt "send everything one way" switch; it must not
    # quietly undo an accuracy assignment.
    monkeypatch.setenv("ARTIK_PRIMARY_MODEL", "astra")
    m = importlib.reload(models)
    assert m.PRIMARY == "openai"
    assert m.task_provider("extraction") == "anthropic"
    monkeypatch.delenv("ARTIK_PRIMARY_MODEL")
    importlib.reload(models)


def test_no_model_is_consulted_for_market_data():
    # The invented-score fallback is gone; nothing may reintroduce it silently.
    assert not hasattr(app, "_llm_fundamental_row")
    import inspect
    assert "_llm_fundamental_row" not in inspect.getsource(app._fallback_row)


# ── extraction cross-check ───────────────────────────────────────────────────

BASE = {"current_balance": 1200.50, "statement_month": "2026-08",
        "masked_account_number": "4321",
        "lines": [{"amount": -50.00}, {"amount": -25.25}]}


def test_identical_extractions_agree():
    v = app._fin_cross_check(BASE, dict(BASE))
    assert v["status"] == "agreed" and v["checked"] is True and v["differences"] == []


def test_amount_disagreement_is_flagged():
    other = dict(BASE, current_balance=1200.05)          # transposed digits
    v = app._fin_cross_check(BASE, other)
    assert v["status"] == "disagreement"
    assert any(d["field"] == "current_balance" for d in v["differences"])


def test_sign_flip_is_flagged():
    other = dict(BASE, lines=[{"amount": 50.00}, {"amount": -25.25}])
    v = app._fin_cross_check(BASE, other)
    assert any(d["field"] == "sign_disagreement" for d in v["differences"])


def test_missing_line_is_flagged():
    other = dict(BASE, lines=[{"amount": -50.00}])
    v = app._fin_cross_check(BASE, other)
    assert any(d["field"] == "line_count" for d in v["differences"])


def test_date_and_account_disagreements_are_flagged():
    v = app._fin_cross_check(BASE, dict(BASE, statement_month="2026-07",
                                        masked_account_number="1234"))
    fields = {d["field"] for d in v["differences"]}
    assert {"statement_month", "masked_account_number"} <= fields


def test_no_second_extraction_is_reported_as_unverified():
    v = app._fin_cross_check(BASE, None)
    assert v["status"] == "unverified" and v["checked"] is False


def test_formatted_money_strings_compare_equal():
    v = app._fin_cross_check({"current_balance": "$1,200.50", "lines": []},
                             {"current_balance": 1200.5, "lines": []})
    assert v["status"] == "agreed"
