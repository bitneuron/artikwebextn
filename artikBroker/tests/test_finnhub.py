"""Tests for the Finnhub intelligence client + signal computation."""
from __future__ import annotations

import types

import finnhub
import intelligence as I


def _resp(status, payload=None, text=""):
    class R:
        status_code = status
        def json(self):
            return payload if payload is not None else {}
    R.text = text
    return R()


def _boom(*a, **k):
    raise TimeoutError("timed out")


# ── client ────────────────────────────────────────────────────────────────────
def test_configured_and_missing_key():
    assert finnhub.FinnhubClient(key="k").configured
    assert not finnhub.FinnhubClient(key="").configured
    try:
        finnhub.FinnhubClient(key="")._get("/x")
        assert False
    except finnhub.FinnhubError as e:
        assert "not configured" in str(e)


def test_success_token_and_header(monkeypatch):
    seen = {}

    def get(url, params, headers, timeout):
        seen.update(params=params, headers=headers)
        return _resp(200, [{"a": 1}])
    monkeypatch.setattr(finnhub, "requests", types.SimpleNamespace(get=get))
    finnhub._CACHE.clear()
    d = finnhub.FinnhubClient(key="SECRET").recommendation_trends("AAPL")
    assert d == [{"a": 1}]
    assert seen["params"]["token"] == "SECRET"           # query auth
    assert seen["headers"]["X-Finnhub-Token"] == "SECRET"  # header auth


def test_cache_reduces_calls(monkeypatch):
    calls = {"n": 0}

    def get(*a, **k):
        calls["n"] += 1
        return _resp(200, {"ok": 1})
    monkeypatch.setattr(finnhub, "requests", types.SimpleNamespace(get=get))
    finnhub._CACHE.clear()
    c = finnhub.FinnhubClient(key="k")
    c.filings("AAPL")
    c.filings("AAPL")
    assert calls["n"] == 1                                # 2nd served from cache


def test_timeout_wrapped(monkeypatch):
    monkeypatch.setattr(finnhub, "requests", types.SimpleNamespace(get=_boom))
    finnhub._CACHE.clear()
    try:
        finnhub.FinnhubClient(key="k", retries=1).company_news("AAPL")
        assert False
    except finnhub.FinnhubError as e:
        assert "error" in str(e).lower()


def test_rate_limit(monkeypatch):
    monkeypatch.setattr(finnhub, "requests",
                        types.SimpleNamespace(get=lambda *a, **k: _resp(429, text="limit")))
    finnhub._CACHE.clear()
    try:
        finnhub.FinnhubClient(key="k", retries=1).company_news("AAPL")
        assert False
    except finnhub.FinnhubError as e:
        assert "429" in str(e)


def test_key_never_leaks(monkeypatch):
    key = "SUPERSECRET123456"
    monkeypatch.setattr(finnhub, "requests",
                        types.SimpleNamespace(get=lambda *a, **k: _resp(401, text=f"bad token {key}")))
    finnhub._CACHE.clear()
    try:
        finnhub.FinnhubClient(key=key, retries=0).company_news("AAPL")
        assert False
    except finnhub.FinnhubError as e:
        assert key not in str(e)


def test_bundle_resilient(monkeypatch):
    def get(url, params, headers, timeout):
        if "insider" in url:
            raise RuntimeError("boom")
        return _resp(200, [{"ok": 1}])
    monkeypatch.setattr(finnhub, "requests", types.SimpleNamespace(get=get))
    finnhub._CACHE.clear()
    b = finnhub.FinnhubClient(key="k", retries=0).bundle("AAPL")
    assert b["ok"]
    assert any("insider" in kk for kk in b["errors"])


# ── intelligence signals ────────────────────────────────────────────────────
def test_signals_and_composite_in_range():
    bundle = {"data": {
        "recommendations": [{"period": "2026-07", "strongBuy": 15, "buy": 10, "hold": 5, "sell": 1, "strongSell": 0},
                            {"period": "2026-06", "strongBuy": 12, "buy": 9, "hold": 6, "sell": 2, "strongSell": 1}],
        "insider_transactions": {"data": [{"name": "CEO", "transactionCode": "P", "change": 10000},
                                          {"name": "CFO", "transactionCode": "S", "change": -2000}]},
        "insider_sentiment": {"data": [{"mspr": 45.0}]},
        "fund_ownership": {"ownership": [{"name": "Vanguard", "change": 500000}, {"name": "BlackRock", "change": -100000}]},
        "earnings": [{"period": "Q2", "surprisePercent": 7.5, "actual": 4.3, "estimate": 4.0}],
        "filings": [{"form": "10-Q", "filedDate": "2026-05-01"}],
        "company_news": [{"headline": "beats and raises guidance", "summary": "strong growth"}],
    }}
    s = I.build_intelligence(bundle)
    for k in ("news", "analyst", "insider", "institutional", "sec", "earnings", "composite"):
        assert 0 <= s[k]["score"] <= 100, f"{k} out of range: {s[k]['score']}"
        assert s[k]["signal"] in ("Bullish", "Neutral", "Bearish")
    assert s["insider"]["net"] == 8000
    assert s["institutional"]["trend"] in ("Accumulation", "Distribution", "Neutral")


def test_empty_bundle_is_graceful():
    s = I.build_intelligence({"data": {}})
    assert s["composite"]["score"] == 50 and s["composite"]["signal"] == "Neutral"
    assert s["news"]["available"] is False
    assert s["analyst"]["available"] is False
