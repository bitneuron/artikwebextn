"""Tests for the Interactive Brokers (IBKR) Client Portal client."""
from __future__ import annotations

import types

import ibkr


class _Resp:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._p = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._p


def test_not_configured():
    cl = ibkr.IBKRClient(base_url="")
    assert cl.configured is False
    try:
        cl.auth_status()
        assert False, "expected IBKRError"
    except ibkr.IBKRError as e:
        assert "not configured" in str(e)


def test_configured_and_auth_status(monkeypatch):
    seen = {}

    def request(method, url, params=None, json=None, timeout=None, verify=None):
        seen.update(method=method, url=url, verify=verify)
        return _Resp(200, {"authenticated": True, "competing": False})
    monkeypatch.setattr(ibkr, "requests", types.SimpleNamespace(request=request))
    cl = ibkr.IBKRClient(base_url="https://gw:5000/v1/api", verify_ssl=False)
    assert cl.configured
    st = cl.auth_status()
    assert st["authenticated"] is True
    assert seen["method"] == "POST" and seen["url"].endswith("/iserver/auth/status")
    assert seen["verify"] is False          # self-signed gateway cert


def test_accounts_and_positions(monkeypatch):
    def request(method, url, params=None, json=None, timeout=None, verify=None):
        if url.endswith("/portfolio/accounts"):
            return _Resp(200, [{"accountId": "U123", "desc": "Individual"}])
        if "/positions/" in url:
            return _Resp(200, [{"ticker": "AAPL", "position": 10, "mktValue": 1900, "avgCost": 150, "unrealizedPnl": 400}])
        return _Resp(200, {})
    monkeypatch.setattr(ibkr, "requests", types.SimpleNamespace(request=request))
    cl = ibkr.IBKRClient(base_url="https://gw:5000/v1/api")
    assert cl.accounts()[0]["accountId"] == "U123"
    pos = cl.positions("U123", 0)
    assert pos[0]["ticker"] == "AAPL"


def test_conid_lookup_and_order(monkeypatch):
    calls = []

    def request(method, url, params=None, json=None, timeout=None, verify=None):
        calls.append((method, url, json))
        if url.endswith("/iserver/secdef/search"):
            return _Resp(200, [{"conid": "265598", "symbol": "AAPL"}])
        if "/orders" in url:
            return _Resp(200, [{"id": "reply-1", "message": ["Confirm your order"]}])
        if "/reply/" in url:
            return _Resp(200, [{"order_id": "o-9", "order_status": "Submitted"}])
        return _Resp(200, {})
    monkeypatch.setattr(ibkr, "requests", types.SimpleNamespace(request=request))
    cl = ibkr.IBKRClient(base_url="https://gw:5000/v1/api")
    assert cl.conid_for("AAPL", "STK") == "265598"
    placed = cl.place_order("U123", {"conid": 265598, "orderType": "MKT", "side": "BUY", "quantity": 1, "tif": "DAY"})
    assert placed[0]["id"] == "reply-1"      # confirmation prompt
    done = cl.reply("reply-1", True)
    assert done[0]["order_status"] == "Submitted"


def test_401_gives_reauth_hint(monkeypatch):
    monkeypatch.setattr(ibkr, "requests",
                        types.SimpleNamespace(request=lambda *a, **k: _Resp(401, text="no session")))
    cl = ibkr.IBKRClient(base_url="https://gw:5000/v1/api")
    try:
        cl.accounts()
        assert False
    except ibkr.IBKRError as e:
        assert "not authenticated" in str(e).lower()


def test_mask():
    assert ibkr.mask("") == "(unset)"
    m = ibkr.mask("U1234567890ABC")
    assert m != "U1234567890ABC" and "U12345" in m
