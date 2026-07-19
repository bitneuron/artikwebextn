"""E*TRADE OAuth 1.0a client.

Three-legged OAuth: request token → user authorizes at etrade.com and gets a verifier
code → exchange for an access token → call the account APIs. Signing is HMAC-SHA1 done
with the stdlib (no external OAuth dependency).

Secrets come ONLY from the environment — never hardcoded:
    ETRADE_CONSUMER_KEY, ETRADE_CONSUMER_SECRET, ETRADE_ENV (sandbox|live)

Sandbox base is https://apisb.etrade.com; live is https://api.etrade.com. The authorize
step always uses us.etrade.com. Access tokens expire end-of-day ET (re-connect needed).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
import uuid
from urllib.parse import parse_qsl, quote

try:  # requests is present in the Broker image; guarded so unit tests can import w/o it
    import requests
except Exception:  # noqa: BLE001
    requests = None  # type: ignore

AUTHORIZE_URL = "https://us.etrade.com/e/t/etws/authorize"


class ETradeError(Exception):
    pass


def _pct(s) -> str:
    """RFC-3986 percent-encoding used throughout OAuth 1.0a."""
    return quote(str(s), safe="~")


def signature_base_string(method: str, url: str, params: dict) -> str:
    encoded = "&".join(f"{_pct(k)}={_pct(v)}" for k, v in sorted(params.items()))
    return "&".join([method.upper(), _pct(url), _pct(encoded)])


class ETradeClient:
    def __init__(self, key: str | None = None, secret: str | None = None, env: str | None = None):
        self.key = key if key is not None else os.environ.get("ETRADE_CONSUMER_KEY", "")
        self.secret = secret if secret is not None else os.environ.get("ETRADE_CONSUMER_SECRET", "")
        self.env = (env or os.environ.get("ETRADE_ENV", "sandbox") or "sandbox").lower()
        self.base = ("https://api.etrade.com" if self.env in ("live", "prod", "production")
                     else "https://apisb.etrade.com")

    @property
    def configured(self) -> bool:
        return bool(self.key and self.secret)

    # ── signing ────────────────────────────────────────────────────────────────
    def _oauth_params(self, extra: dict | None = None) -> dict:
        p = {
            "oauth_consumer_key": self.key,
            "oauth_nonce": uuid.uuid4().hex,
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": str(int(time.time())),
            "oauth_version": "1.0",
        }
        if extra:
            p.update(extra)
        return p

    def _sign(self, method: str, url: str, params: dict, token_secret: str = "") -> str:
        base = signature_base_string(method, url, params)
        key = f"{_pct(self.secret)}&{_pct(token_secret)}"
        digest = hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()
        return base64.b64encode(digest).decode()

    def _auth_header(self, method: str, url: str, oauth: dict,
                     token_secret: str = "", query: dict | None = None) -> str:
        all_params = dict(oauth)
        if query:
            all_params.update(query)
        signed = dict(oauth)
        signed["oauth_signature"] = self._sign(method, url, all_params, token_secret)
        return "OAuth " + ", ".join(f'{_pct(k)}="{_pct(v)}"' for k, v in sorted(signed.items()))

    # ── HTTP ─────────────────────────────────────────────────────────────────
    def _get(self, url: str, oauth: dict, token_secret: str = "", query: dict | None = None):
        if requests is None:
            raise ETradeError("the 'requests' library is not available")
        header = self._auth_header("GET", url, oauth, token_secret, query)
        return requests.get(url, headers={"Authorization": header, "Accept": "application/json"},
                            params=query, timeout=25)

    def _post(self, url: str, oauth: dict, token_secret: str = "", json_body: dict | None = None):
        # OAuth 1.0a: a JSON request body is NOT part of the signature (only form-encoded
        # bodies would be) — the signature covers method + url + oauth params.
        if requests is None:
            raise ETradeError("the 'requests' library is not available")
        header = self._auth_header("POST", url, oauth, token_secret)
        return requests.post(url, headers={"Authorization": header, "Accept": "application/json",
                                           "Content-Type": "application/json"},
                             json=json_body, timeout=30)

    # ── OAuth flow ─────────────────────────────────────────────────────────────
    def get_request_token(self) -> tuple[str, str]:
        url = f"{self.base}/oauth/request_token"
        r = self._get(url, self._oauth_params({"oauth_callback": "oob"}))
        if r.status_code != 200:
            raise ETradeError(f"request_token failed: HTTP {r.status_code} {r.text[:200]}")
        d = dict(parse_qsl(r.text))
        if "oauth_token" not in d:
            raise ETradeError(f"request_token: unexpected response {r.text[:200]}")
        return d["oauth_token"], d["oauth_token_secret"]

    def authorize_url(self, request_token: str) -> str:
        return f"{AUTHORIZE_URL}?key={_pct(self.key)}&token={_pct(request_token)}"

    def get_access_token(self, req_token: str, req_secret: str, verifier: str) -> tuple[str, str]:
        url = f"{self.base}/oauth/access_token"
        oauth = self._oauth_params({"oauth_token": req_token, "oauth_verifier": verifier})
        r = self._get(url, oauth, token_secret=req_secret)
        if r.status_code != 200:
            raise ETradeError(f"access_token failed: HTTP {r.status_code} {r.text[:200]}")
        d = dict(parse_qsl(r.text))
        if "oauth_token" not in d:
            raise ETradeError(f"access_token: unexpected response {r.text[:200]}")
        return d["oauth_token"], d["oauth_token_secret"]

    # ── resource APIs ──────────────────────────────────────────────────────────
    def api_get(self, path: str, token: str, secret: str, query: dict | None = None) -> dict:
        url = f"{self.base}{path}"
        r = self._get(url, self._oauth_params({"oauth_token": token}), token_secret=secret, query=query)
        if r.status_code == 204:
            return {}
        if r.status_code != 200:
            raise ETradeError(f"{path} failed: HTTP {r.status_code} {r.text[:200]}")
        try:
            return r.json()
        except Exception:  # noqa: BLE001
            return {"raw": r.text}

    def api_post(self, path: str, token: str, secret: str, json_body: dict) -> dict:
        url = f"{self.base}{path}"
        r = self._post(url, self._oauth_params({"oauth_token": token}), token_secret=secret,
                       json_body=json_body)
        if r.status_code not in (200, 201):
            raise ETradeError(f"{path} failed: HTTP {r.status_code} {r.text[:300]}")
        try:
            return r.json()
        except Exception:  # noqa: BLE001
            return {"raw": r.text}

    def list_accounts(self, token: str, secret: str) -> dict:
        return self.api_get("/v1/accounts/list.json", token, secret)

    def balance(self, token: str, secret: str, account_id_key: str,
                inst_type: str = "BROKERAGE") -> dict:
        return self.api_get(f"/v1/accounts/{account_id_key}/balance.json", token, secret,
                            query={"instType": inst_type, "realTimeNAV": "true"})

    def portfolio(self, token: str, secret: str, account_id_key: str) -> dict:
        # totalsRequired adds the account-level Totals block (day's + total gain/loss).
        return self.api_get(f"/v1/accounts/{account_id_key}/portfolio.json", token, secret,
                            query={"totalsRequired": "true", "count": "200"})

    def list_orders(self, token: str, secret: str, account_id_key: str, count: int = 25) -> dict:
        return self.api_get(f"/v1/accounts/{account_id_key}/orders.json", token, secret,
                            query={"count": str(count)})

    # ── order placement (equities): preview → place, both required by E*TRADE ──
    @staticmethod
    def _order_entry(symbol: str, action: str, quantity: int, price_type: str,
                     limit_price, order_term: str) -> dict:
        return {
            "allOrNone": "false",
            "priceType": price_type,
            "orderTerm": order_term,
            "marketSession": "REGULAR",
            "stopPrice": "",
            "limitPrice": str(limit_price) if price_type == "LIMIT" else "",
            "Instrument": [{
                "Product": {"securityType": "EQ", "symbol": symbol},
                "orderAction": action,
                "quantityType": "QUANTITY",
                "quantity": str(int(quantity)),
            }],
        }

    def preview_order(self, token: str, secret: str, account_id_key: str, *, symbol: str,
                      action: str, quantity: int, price_type: str = "MARKET",
                      limit_price=None, order_term: str = "GOOD_FOR_DAY") -> dict:
        """Step 1 of 2. Returns E*TRADE's preview (estimated cost/commission + previewId)
        plus `_client_order_id`/`_order` which MUST be echoed back into place_order."""
        client_order_id = uuid.uuid4().hex[:20]
        order = [self._order_entry(symbol, action, quantity, price_type, limit_price, order_term)]
        out = self.api_post(f"/v1/accounts/{account_id_key}/orders/preview.json", token, secret,
                            {"PreviewOrderRequest": {"orderType": "EQ",
                                                     "clientOrderId": client_order_id,
                                                     "Order": order}})
        out["_client_order_id"] = client_order_id
        out["_order"] = order
        return out

    def place_order(self, token: str, secret: str, account_id_key: str, *, preview_id,
                    client_order_id: str, order: list) -> dict:
        """Step 2 of 2 — must reuse the preview's clientOrderId + Order payload verbatim."""
        return self.api_post(f"/v1/accounts/{account_id_key}/orders/place.json", token, secret,
                             {"PlaceOrderRequest": {"orderType": "EQ",
                                                    "clientOrderId": client_order_id,
                                                    "PreviewIds": [{"previewId": preview_id}],
                                                    "Order": order}})
