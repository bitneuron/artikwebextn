"""Tests for the E*TRADE OAuth 1.0a client (signing, URLs, config, response parsing)."""
from __future__ import annotations

import etrade


def test_not_configured_without_keys():
    c = etrade.ETradeClient(key="", secret="", env="sandbox")
    assert c.configured is False
    assert c.base == "https://apisb.etrade.com"


def test_env_selects_base_url():
    assert etrade.ETradeClient(key="k", secret="s", env="sandbox").base == "https://apisb.etrade.com"
    assert etrade.ETradeClient(key="k", secret="s", env="live").base == "https://api.etrade.com"
    assert etrade.ETradeClient(key="k", secret="s", env="production").base == "https://api.etrade.com"
    assert etrade.ETradeClient(key="k", secret="s").configured is True


def test_percent_encoding():
    # unreserved chars pass through; reserved get encoded (RFC 3986)
    assert etrade._pct("a b/c") == "a%20b%2Fc"
    assert etrade._pct("~-_.") == "~-_."


def test_signature_base_string_is_sorted_and_encoded():
    bs = etrade.signature_base_string(
        "get", "https://apisb.etrade.com/oauth/request_token",
        {"oauth_consumer_key": "ck", "oauth_nonce": "n", "oauth_version": "1.0",
         "oauth_callback": "oob"})
    assert bs.startswith("GET&https%3A%2F%2Fapisb.etrade.com%2Foauth%2Frequest_token&")
    # params sorted alphabetically: callback, consumer_key, nonce, version
    assert "oauth_callback%3Doob%26oauth_consumer_key%3Dck" in bs


def test_signature_is_deterministic_and_matches_hmac():
    import base64, hashlib, hmac
    c = etrade.ETradeClient(key="ck", secret="cs", env="sandbox")
    params = {"oauth_consumer_key": "ck", "oauth_nonce": "n", "oauth_timestamp": "1",
              "oauth_signature_method": "HMAC-SHA1", "oauth_version": "1.0"}
    url = "https://apisb.etrade.com/oauth/request_token"
    sig = c._sign("GET", url, params, token_secret="")
    base = etrade.signature_base_string("GET", url, params)
    expected = base64.b64encode(hmac.new(b"cs&", base.encode(), hashlib.sha1).digest()).decode()
    assert sig == expected
    # token secret is included in the signing key
    sig2 = c._sign("GET", url, params, token_secret="ts")
    assert sig2 != sig


def test_auth_header_has_signature_and_quoted_params():
    c = etrade.ETradeClient(key="ck", secret="cs")
    hdr = c._auth_header("GET", "https://apisb.etrade.com/oauth/request_token",
                         c._oauth_params({"oauth_callback": "oob"}))
    assert hdr.startswith("OAuth ")
    assert 'oauth_consumer_key="ck"' in hdr
    assert "oauth_signature=" in hdr and "oauth_callback=" in hdr


def test_authorize_url():
    c = etrade.ETradeClient(key="my key", secret="s")
    url = c.authorize_url("REQ TOK")
    assert url.startswith("https://us.etrade.com/e/t/etws/authorize?key=my%20key&token=REQ%20TOK")


def test_request_token_parsing(monkeypatch):
    c = etrade.ETradeClient(key="ck", secret="cs")

    class _Resp:
        status_code = 200
        text = "oauth_token=TOK&oauth_token_secret=SEC"

    monkeypatch.setattr(c, "_get", lambda *a, **k: _Resp())
    tok, sec = c.get_request_token()
    assert tok == "TOK" and sec == "SEC"


def test_request_token_error(monkeypatch):
    c = etrade.ETradeClient(key="ck", secret="cs")

    class _Resp:
        status_code = 401
        text = "oauth_problem=signature_invalid"

    monkeypatch.setattr(c, "_get", lambda *a, **k: _Resp())
    try:
        c.get_request_token()
        assert False, "expected ETradeError"
    except etrade.ETradeError as e:
        assert "401" in str(e)


def test_api_get_parses_json(monkeypatch):
    c = etrade.ETradeClient(key="ck", secret="cs")

    class _Resp:
        status_code = 200
        def json(self):
            return {"AccountListResponse": {"Accounts": {"Account": [{"accountId": "1"}]}}}

    monkeypatch.setattr(c, "_get", lambda *a, **k: _Resp())
    data = c.list_accounts("t", "s")
    assert data["AccountListResponse"]["Accounts"]["Account"][0]["accountId"] == "1"
