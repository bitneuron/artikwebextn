"""Tests for the Charles Schwab OAuth 2.0 client (config, authorize URL, token, parsing)."""
from __future__ import annotations

import base64
import types

import schwab


def test_configured_toggle():
    assert schwab.SchwabClient(app_key="k", app_secret="s", redirect_uri="https://x/cb").configured
    assert not schwab.SchwabClient(app_key="", app_secret="s", redirect_uri="https://x/cb").configured
    assert not schwab.SchwabClient(app_key="k", app_secret="s", redirect_uri="").configured


def test_authorize_url():
    c = schwab.SchwabClient(app_key="AK", app_secret="AS", redirect_uri="https://h/api/schwab/callback")
    u = c.authorize_url("STATE")
    assert u.startswith("https://api.schwabapi.com/v1/oauth/authorize?")
    assert "client_id=AK" in u and "response_type=code" in u and "state=STATE" in u
    assert "redirect_uri=https%3A%2F%2Fh%2Fapi%2Fschwab%2Fcallback" in u


def test_basic_auth_header():
    c = schwab.SchwabClient(app_key="AK", app_secret="AS", redirect_uri="x")
    assert base64.b64decode(c._basic()).decode() == "AK:AS"


def _resp(status, payload=None, text=""):
    class R:
        status_code = status
        def json(self):
            return payload if payload is not None else {}
    R.text = text
    return R()


def test_token_exchange(monkeypatch):
    captured = {}

    def fake_post(url, data, timeout, headers):
        captured.update(url=url, data=data, auth=headers.get("Authorization"))
        return _resp(200, {"access_token": "AT", "refresh_token": "RT", "expires_in": 1800})

    monkeypatch.setattr(schwab, "requests", types.SimpleNamespace(post=fake_post, get=None))
    tok = schwab.SchwabClient("AK", "AS", "x").exchange_code("CODE")
    assert tok["access_token"] == "AT" and tok["refresh_token"] == "RT"
    assert captured["data"]["grant_type"] == "authorization_code"
    assert captured["data"]["code"] == "CODE"
    assert captured["auth"].startswith("Basic ")


def test_refresh_and_error(monkeypatch):
    monkeypatch.setattr(schwab, "requests",
                        types.SimpleNamespace(post=lambda *a, **k: _resp(200, {"access_token": "AT2", "expires_in": 1800}),
                                              get=None))
    assert schwab.SchwabClient("AK", "AS", "x").refresh("RT")["access_token"] == "AT2"
    monkeypatch.setattr(schwab, "requests",
                        types.SimpleNamespace(post=lambda *a, **k: _resp(400, text="bad"), get=None))
    try:
        schwab.SchwabClient("AK", "AS", "x").refresh("RT")
        assert False, "expected SchwabError"
    except schwab.SchwabError as e:
        assert "400" in str(e)


def test_accounts_parsing(monkeypatch):
    accts_payload = [{"securitiesAccount": {"accountNumber": "111", "positions": []}}]
    monkeypatch.setattr(schwab, "requests",
                        types.SimpleNamespace(get=lambda *a, **k: _resp(200, accts_payload), post=None))
    accts = schwab.SchwabClient("AK", "AS", "x").accounts("AT")
    assert accts[0]["securitiesAccount"]["accountNumber"] == "111"
