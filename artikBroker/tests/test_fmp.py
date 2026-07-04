"""Tests for the Financial Modeling Prep client (auth, retry, errors, key masking)."""
from __future__ import annotations

import types

import fmp


def _resp(status, payload=None, text=""):
    class R:
        status_code = status
        def json(self):
            return payload if payload is not None else {}
    R.text = text
    return R()


def test_configured_and_missing_key():
    assert fmp.FMPClient(key="k").configured
    assert not fmp.FMPClient(key="").configured
    try:
        fmp.FMPClient(key="")._get("/profile", {"symbol": "AAPL"})
        assert False, "expected FMPError"
    except fmp.FMPError as e:
        assert "not configured" in str(e)


def test_success_uses_header_and_query_auth(monkeypatch):
    seen = {}

    def get(url, params, headers, timeout):
        seen.update(url=url, params=params, headers=headers)
        return _resp(200, [{"symbol": "AAPL", "price": 195}])

    monkeypatch.setattr(fmp, "requests", types.SimpleNamespace(get=get))
    d = fmp.FMPClient(key="SECRETKEY").profile("AAPL")
    assert d[0]["symbol"] == "AAPL"
    assert seen["params"]["apikey"] == "SECRETKEY"     # query auth
    assert seen["headers"]["apikey"] == "SECRETKEY"    # header auth
    assert seen["url"].endswith("/profile")


def test_timeout_is_wrapped(monkeypatch):
    def get(*a, **k):
        raise TimeoutError("timed out")
    monkeypatch.setattr(fmp, "requests", types.SimpleNamespace(get=get))
    try:
        fmp.FMPClient(key="k", retries=1).quote("AAPL")
        assert False, "expected FMPError"
    except fmp.FMPError as e:
        assert "error" in str(e).lower()


def test_rate_limit_error(monkeypatch):
    monkeypatch.setattr(fmp, "requests",
                        types.SimpleNamespace(get=lambda *a, **k: _resp(429, text="limit")))
    try:
        fmp.FMPClient(key="k", retries=1).quote("AAPL")
        assert False, "expected FMPError"
    except fmp.FMPError as e:
        assert "429" in str(e)


def test_api_key_never_leaks_into_errors(monkeypatch):
    key = "SUPERSECRETKEY123"
    monkeypatch.setattr(fmp, "requests",
                        types.SimpleNamespace(get=lambda *a, **k: _resp(401, text=f"invalid apikey {key}")))
    try:
        fmp.FMPClient(key=key, retries=0).quote("AAPL")
        assert False, "expected FMPError"
    except fmp.FMPError as e:
        assert key not in str(e)                       # masked out
    m = fmp.mask_key(key)
    assert m != key and key[:4] in m and key not in m


def test_bundle_is_resilient(monkeypatch):
    def get(url, params, headers, timeout):
        if "quote" in url:
            raise RuntimeError("boom")
        return _resp(200, [{"ok": 1}])
    monkeypatch.setattr(fmp, "requests", types.SimpleNamespace(get=get))
    b = fmp.FMPClient(key="k", retries=0).bundle("AAPL")
    assert b["ok"] is True
    assert "quote" in b["errors"]                      # one dataset failed
    assert "profile" in b["data"]                      # others still succeeded
