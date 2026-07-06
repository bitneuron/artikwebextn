"""Tests for the IBKR OAuth 1.0a signer (request-signing path; DH/LST needs real keys)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
from urllib.parse import unquote

import ibkr_oauth


def test_not_configured(monkeypatch):
    for k in ("IBKR_OAUTH_CONSUMER_KEY", "IBKR_OAUTH_ACCESS_TOKEN", "IBKR_OAUTH_ACCESS_TOKEN_SECRET",
              "IBKR_OAUTH_SIGNATURE_KEY", "IBKR_OAUTH_ENCRYPTION_KEY", "IBKR_OAUTH_DH_PRIME"):
        monkeypatch.delenv(k, raising=False)
    assert ibkr_oauth.IBKROAuth().configured is False


def test_to_bytes_java_bigint():
    f = ibkr_oauth.IBKROAuth._to_bytes
    assert f(1) == b"\x01"
    assert f(127) == b"\x7f"
    assert f(255) == b"\x00\xff"      # MSB set → leading 0x00 (Java BigInteger.toByteArray)
    assert f(256) == b"\x01\x00"


def test_base_string_rfc3986():
    b = ibkr_oauth.IBKROAuth._base_string("get", "https://api.ibkr.com/v1/api/x",
                                          {"b": "2", "a": "1"})
    assert b.startswith("GET&")
    assert "a%3D1%26b%3D2" in b          # sorted + percent-encoded


def test_auth_header_hmac_signature(monkeypatch):
    monkeypatch.setenv("IBKR_OAUTH_CONSUMER_KEY", "ck")
    monkeypatch.setenv("IBKR_OAUTH_ACCESS_TOKEN", "tok")
    o = ibkr_oauth.IBKROAuth()
    lst = base64.b64encode(b"a-live-session-token").decode()
    o._lst, o._lst_exp = lst, 1e18       # inject a known LST (bypass the DH exchange)
    monkeypatch.setattr(ibkr_oauth._secrets, "token_hex", lambda n: "NONCE")
    monkeypatch.setattr(ibkr_oauth.time, "time", lambda: 1000)

    url = "https://api.ibkr.com/v1/api/portfolio/accounts"
    hdr = o.auth_header("GET", url, {})
    got = unquote(re.search(r'oauth_signature="([^"]+)"', hdr).group(1))

    params = {"oauth_consumer_key": "ck", "oauth_nonce": "NONCE",
              "oauth_signature_method": "HMAC-SHA256", "oauth_timestamp": "1000", "oauth_token": "tok"}
    base = ibkr_oauth.IBKROAuth._base_string("GET", url, params)
    expected = base64.b64encode(hmac.new(base64.b64decode(lst), base.encode(), hashlib.sha256).digest()).decode()
    assert got == expected
    assert 'oauth_signature_method="HMAC-SHA256"' in hdr and 'realm="limited_poa"' in hdr


def test_client_uses_oauth_when_configured(monkeypatch):
    import types
    import ibkr
    monkeypatch.setenv("IBKR_OAUTH_CONSUMER_KEY", "ck")
    monkeypatch.setenv("IBKR_OAUTH_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("IBKR_OAUTH_ACCESS_TOKEN_SECRET", "x")
    monkeypatch.setenv("IBKR_OAUTH_SIGNATURE_KEY", "pem")
    monkeypatch.setenv("IBKR_OAUTH_ENCRYPTION_KEY", "pem")
    monkeypatch.setenv("IBKR_OAUTH_DH_PRIME", "ff")
    monkeypatch.delenv("IBKR_BASE_URL", raising=False)
    cl = ibkr.IBKRClient()
    assert cl.oauth_mode is True and cl.configured is True
    # a request should attach an Authorization header (signing stubbed)
    seen = {}

    def request(method, url, params=None, json=None, headers=None, timeout=None, verify=None):
        seen.update(headers=headers, verify=verify)
        class R:
            status_code = 200
            def json(self): return {"authenticated": True}
        return R()
    monkeypatch.setattr(ibkr, "requests", types.SimpleNamespace(request=request))
    cl.oauth.auth_header = lambda m, u, q: "OAuth signed"
    cl.auth_status()
    assert seen["headers"]["Authorization"] == "OAuth signed"
    assert seen["verify"] is True        # real TLS for api.ibkr.com
