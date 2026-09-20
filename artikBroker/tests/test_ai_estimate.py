"""The AI estimate fallback: useful when data is unavailable, never mistaken for a score."""
from __future__ import annotations

import app


EST = {"ticker": "AAA", "data_source": "ai_estimate", "estimated_band": "strong",
       "score": None, "status": None, "rating": None, "error": None}
REAL = {"ticker": "BBB", "score": 80, "status": "BUY"}
WEAK = {"ticker": "CCC", "score": 40, "status": "SELL"}


def test_estimate_never_carries_engine_fields():
    assert EST["score"] is None and EST["status"] is None and EST["rating"] is None


def test_estimate_is_allowed_through_when_no_numeric_filter():
    assert app._passes(EST, {}) is True


def test_estimate_is_excluded_by_a_score_filter():
    # It cannot honestly satisfy "score > 80", so it must not appear to.
    assert app._passes(EST, {"score_min": 80}) is False
    assert app._passes(EST, {"score_max": 50}) is False


def test_estimate_is_excluded_by_an_rsi_or_status_filter():
    assert app._passes(EST, {"rsi_max": 30}) is False
    assert app._passes(EST, {"status": "BUY"}) is False


def test_real_rows_still_filter_normally():
    assert app._passes(REAL, {"score_min": 75}) is True
    assert app._passes(WEAK, {"score_min": 75}) is False
    assert app._passes({"ticker": "X", "error": "boom"}, {}) is False


def test_estimates_never_outrank_a_real_score():
    rows = [dict(EST), dict(WEAK), dict(REAL)]
    _BAND = {"strong": 0, "mixed": 1, "weak": 2}
    rows.sort(key=lambda r: (r.get("data_source") == "ai_estimate",
                             _BAND.get(r.get("estimated_band"), 3)
                             if r.get("data_source") == "ai_estimate" else -(r.get("score") or 0)))
    assert [r["ticker"] for r in rows] == ["BBB", "CCC", "AAA"]   # estimate last, always


def test_bands_are_the_only_accepted_reads():
    assert app._ESTIMATE_BANDS == ("strong", "mixed", "weak")


def test_prompt_forbids_score_and_rating_and_allows_declining():
    s = app._ESTIMATE_SYSTEM
    assert "not live" in s
    assert "Do NOT return a numeric score" in s
    assert "buy/hold/sell rating" in s
    assert "known=false" in s and "Declining is a valid" in s


def test_bulk_scans_do_not_call_a_model(monkeypatch):
    called = []
    monkeypatch.setattr(app, "_av_fundamental_row", lambda t: None)
    monkeypatch.setattr(app, "_llm_estimate_row", lambda t: called.append(t) or None)
    app._fallback_row("AAA", "no data", allow_llm=False)
    assert called == []                       # index sweeps stay model-free
    app._fallback_row("AAA", "no data", allow_llm=True)
    assert called == ["AAA"]


def test_a_declining_model_yields_data_unavailable(monkeypatch):
    # The model said it does not know the company. That must stay "no data", not
    # become a guess. A real price may still be attached from a verified source.
    monkeypatch.setattr(app, "_av_fundamental_row", lambda t: None)
    monkeypatch.setattr(app, "_llm_estimate_row", lambda t: None)
    monkeypatch.setattr(app.av, "global_quote", lambda t: {})
    row = app._fallback_row("ZZZ", "no data returned")
    assert row["error"] == "no data returned"
    assert "score" not in row and "estimated_band" not in row
