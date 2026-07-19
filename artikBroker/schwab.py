"""Charles Schwab Trader API — OAuth 2.0 (authorization-code) client.

Unlike E*TRADE (OAuth 1.0a + PIN), Schwab uses OAuth 2.0: redirect the user to Schwab
to authorize, Schwab redirects back to our callback with a `code`, we exchange it for an
access token (~30 min) + refresh token (~7 days). Access tokens are refreshed silently.

Secrets come ONLY from the environment — never hardcoded:
    SCHWAB_APP_KEY, SCHWAB_APP_SECRET, SCHWAB_REDIRECT_URI

Endpoints (subject to Schwab revising — verified against developer.schwab.com):
    authorize : https://api.schwabapi.com/v1/oauth/authorize
    token     : https://api.schwabapi.com/v1/oauth/token
    accounts  : https://api.schwabapi.com/trader/v1/accounts
"""
from __future__ import annotations

import base64
import os
from urllib.parse import urlencode

try:  # requests is present in the Broker image; guarded so unit tests import w/o it
    import requests
except Exception:  # noqa: BLE001
    requests = None  # type: ignore

AUTHORIZE_URL = "https://api.schwabapi.com/v1/oauth/authorize"
TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"
API_BASE = "https://api.schwabapi.com"


class SchwabError(Exception):
    pass


class SchwabClient:
    def __init__(self, app_key: str | None = None, app_secret: str | None = None,
                 redirect_uri: str | None = None):
        self.key = app_key if app_key is not None else os.environ.get("SCHWAB_APP_KEY", "")
        self.secret = app_secret if app_secret is not None else os.environ.get("SCHWAB_APP_SECRET", "")
        self.redirect_uri = (redirect_uri if redirect_uri is not None
                             else os.environ.get("SCHWAB_REDIRECT_URI", ""))

    @property
    def configured(self) -> bool:
        return bool(self.key and self.secret and self.redirect_uri)

    # ── OAuth 2.0 ──────────────────────────────────────────────────────────────
    def authorize_url(self, state: str) -> str:
        return AUTHORIZE_URL + "?" + urlencode({
            "client_id": self.key,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "state": state,
        })

    def _basic(self) -> str:
        return base64.b64encode(f"{self.key}:{self.secret}".encode()).decode()

    def _token(self, data: dict) -> dict:
        if requests is None:
            raise SchwabError("the 'requests' library is not available")
        r = requests.post(TOKEN_URL, data=data, timeout=20, headers={
            "Authorization": f"Basic {self._basic()}",
            "Content-Type": "application/x-www-form-urlencoded"})
        if r.status_code != 200:
            raise SchwabError(f"token request failed: HTTP {r.status_code} {r.text[:200]}")
        return r.json()

    def exchange_code(self, code: str) -> dict:
        """Authorization code → {access_token, refresh_token, expires_in, ...}."""
        return self._token({"grant_type": "authorization_code", "code": code,
                            "redirect_uri": self.redirect_uri})

    def refresh(self, refresh_token: str) -> dict:
        """Refresh token → a fresh access token (+ possibly a new refresh token)."""
        return self._token({"grant_type": "refresh_token", "refresh_token": refresh_token})

    # ── resource APIs ──────────────────────────────────────────────────────────
    def api_get(self, path: str, access_token: str, params: dict | None = None) -> dict | list:
        if requests is None:
            raise SchwabError("the 'requests' library is not available")
        r = requests.get(API_BASE + path, params=params, timeout=25, headers={
            "Authorization": f"Bearer {access_token}", "Accept": "application/json"})
        if r.status_code != 200:
            raise SchwabError(f"{path} failed: HTTP {r.status_code} {r.text[:200]}")
        try:
            return r.json()
        except Exception:  # noqa: BLE001
            return {"raw": r.text}

    def api_post(self, path: str, access_token: str, json_body: dict) -> dict:
        if requests is None:
            raise SchwabError("the 'requests' library is not available")
        r = requests.post(API_BASE + path, json=json_body, timeout=30, headers={
            "Authorization": f"Bearer {access_token}", "Accept": "application/json",
            "Content-Type": "application/json"})
        if r.status_code not in (200, 201):
            raise SchwabError(f"{path} failed: HTTP {r.status_code} {r.text[:300]}")
        out = {"status": r.status_code, "location": r.headers.get("Location") or ""}
        try:
            if r.text:
                out["body"] = r.json()
        except Exception:  # noqa: BLE001
            pass
        return out

    def accounts(self, access_token: str, positions: bool = True) -> list:
        data = self.api_get("/trader/v1/accounts", access_token,
                            params={"fields": "positions"} if positions else None)
        return data if isinstance(data, list) else [data]

    def account_numbers(self, access_token: str) -> list:
        """[{accountNumber, hashValue}] — order/orders endpoints take the HASH, never the number."""
        data = self.api_get("/trader/v1/accounts/accountNumbers", access_token)
        return data if isinstance(data, list) else [data]

    def orders(self, access_token: str, account_hash: str, from_iso: str, to_iso: str,
               max_results: int = 50) -> list:
        data = self.api_get(f"/trader/v1/accounts/{account_hash}/orders", access_token,
                            params={"fromEnteredTime": from_iso, "toEnteredTime": to_iso,
                                    "maxResults": str(max_results)})
        return data if isinstance(data, list) else [data]

    # ── order placement (equities). Schwab has NO server-side preview endpoint —
    # the app builds the payload once, shows it to the user, and posts it on confirm. ──
    @staticmethod
    def order_payload(symbol: str, instruction: str, quantity: int, order_type: str = "MARKET",
                      limit_price=None, duration: str = "DAY") -> dict:
        p = {
            "orderType": order_type,
            "session": "NORMAL",
            "duration": duration,
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [{
                "instruction": instruction,
                "quantity": int(quantity),
                "instrument": {"symbol": symbol, "assetType": "EQUITY"},
            }],
        }
        if order_type == "LIMIT":
            p["price"] = str(limit_price)
        return p

    def place_order(self, access_token: str, account_hash: str, payload: dict) -> dict:
        """201 on success; the new order id is the tail of the Location header."""
        return self.api_post(f"/trader/v1/accounts/{account_hash}/orders", access_token, payload)

    def quote(self, access_token: str, symbol: str) -> dict:
        """Best-effort last price for the order review (market-data scope may be absent)."""
        return self.api_get(f"/marketdata/v1/{symbol}/quotes", access_token)
