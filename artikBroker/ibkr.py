"""Interactive Brokers (IBKR) — Client Portal Web API client.

IBKR exposes a REST **Client Portal Web API** for viewing accounts/positions and placing
orders (stocks, ETFs, crypto). Unlike E*TRADE (OAuth 1.0a) or Schwab (OAuth 2.0), the Client
Portal API authenticates through the IBKR **Client Portal Gateway**: the user logs into the
gateway once (IBKR SSO in a browser), and the gateway holds the authenticated session — this
app then calls the gateway's REST base for everything. No per-user OAuth tokens are stored.

Configuration (env only — never hardcode / never sent to the client):
    IBKR_BASE_URL       REST base of the gateway, e.g. https://your-host:5000/v1/api
    IBKR_GATEWAY_URL    browser URL where the user authenticates the gateway (login SSO)
    IBKR_VERIFY_SSL     "true"/"false" — gateways use a self-signed cert (default false)
    IBKR_ENV            "paper" | "live" (informational; the gateway decides the real account)

The app is unusable until IBKR_BASE_URL points at a reachable authenticated gateway — until
then everything degrades gracefully ("not configured").
"""
from __future__ import annotations

import os

try:  # requests is present in the Broker image; guarded so unit tests import without it
    import requests
except Exception:  # noqa: BLE001
    requests = None  # type: ignore


def _env(*keys, default=""):
    for k in keys:
        v = os.environ.get(k)
        if v:
            return v
    return default


def mask(s: str) -> str:
    if not s:
        return "(unset)"
    return f"{s[:6]}…{s[-4:]}" if len(s) > 12 else "…"


class IBKRError(Exception):
    pass


class IBKRClient:
    def __init__(self, base_url: str | None = None, verify_ssl: bool | None = None,
                 timeout: float = 12.0):
        self.base = (base_url if base_url is not None else _env("IBKR_BASE_URL")).rstrip("/")
        self.gateway_url = _env("IBKR_GATEWAY_URL")
        self.env = _env("IBKR_ENV", default="paper")
        if verify_ssl is None:
            verify_ssl = _env("IBKR_VERIFY_SSL", default="false").lower() == "true"
        self.verify = verify_ssl
        self.timeout = timeout
        # Optional OAuth 1.0a (hosted Web API) — used when no gateway base is set.
        try:
            import ibkr_oauth
            self.oauth = ibkr_oauth.IBKROAuth()
        except Exception:  # noqa: BLE001
            self.oauth = None
        if not self.base and self.oauth and self.oauth.configured:
            self.base = self.oauth.base

    @property
    def oauth_mode(self) -> bool:
        return bool(self.oauth and self.oauth.configured)

    @property
    def configured(self) -> bool:
        return bool(self.base) or self.oauth_mode

    def _req(self, method: str, path: str, params: dict | None = None, json_body=None):
        if not self.base:
            raise IBKRError("IBKR_BASE_URL is not configured")
        if requests is None:
            raise IBKRError("the 'requests' library is not available")
        url = f"{self.base}{path}"
        headers = {"User-Agent": "artikBroker"}
        verify = self.verify
        if self.oauth_mode:                       # hosted Web API — sign + real TLS
            try:
                headers["Authorization"] = self.oauth.auth_header(method, url, params)
            except Exception as e:  # noqa: BLE001
                raise IBKRError(f"IBKR OAuth signing failed: {e}")
            verify = True
        try:
            r = requests.request(method, url, params=params, json=json_body,
                                  headers=headers, timeout=self.timeout, verify=verify)
        except Exception as e:  # noqa: BLE001
            raise IBKRError(f"IBKR {path} error: {e}")
        if r.status_code == 401:
            raise IBKRError(f"IBKR {path}: not authenticated — log into the Client Portal Gateway")
        if r.status_code >= 400:
            raise IBKRError(f"IBKR {path} HTTP {r.status_code}: {r.text[:160]}")
        try:
            return r.json()
        except ValueError:
            return {}

    # ── session / auth ──────────────────────────────────────────────────────────
    def auth_status(self) -> dict:
        return self._req("POST", "/iserver/auth/status")

    def reauthenticate(self) -> dict:
        return self._req("POST", "/iserver/reauthenticate")

    def tickle(self) -> dict:
        return self._req("POST", "/tickle")

    def logout(self) -> dict:
        return self._req("POST", "/logout")

    # ── accounts / portfolio ────────────────────────────────────────────────────
    def accounts(self) -> list:
        d = self._req("GET", "/portfolio/accounts")
        return d if isinstance(d, list) else (d.get("accounts") if isinstance(d, dict) else []) or []

    def positions(self, account_id: str, page: int = 0) -> list:
        d = self._req("GET", f"/portfolio/{account_id}/positions/{page}")
        return d if isinstance(d, list) else []

    def summary(self, account_id: str) -> dict:
        return self._req("GET", f"/portfolio/{account_id}/summary")

    def ledger(self, account_id: str) -> dict:
        return self._req("GET", f"/portfolio/{account_id}/ledger")

    # ── market data / contracts ─────────────────────────────────────────────────
    def search_contract(self, symbol: str, sec_type: str = "STK") -> list:
        d = self._req("POST", "/iserver/secdef/search",
                      json_body={"symbol": symbol, "name": False, "secType": sec_type})
        return d if isinstance(d, list) else []

    def conid_for(self, symbol: str, sec_type: str = "STK") -> str | None:
        """First matching contract id for a symbol (STK/ETF share secType STK; CRYPTO for crypto)."""
        for c in self.search_contract(symbol, sec_type):
            cid = c.get("conid") or c.get("conidex")
            if cid:
                return str(cid).split("@")[0]
        return None

    def snapshot(self, conids: list[str], fields=("31", "84", "86", "87", "7295")) -> list:
        d = self._req("GET", "/iserver/marketdata/snapshot",
                      params={"conids": ",".join(map(str, conids)), "fields": ",".join(fields)})
        return d if isinstance(d, list) else []

    # ── orders (buy / sell) ─────────────────────────────────────────────────────
    def place_order(self, account_id: str, order: dict) -> list:
        """order: {conid, orderType(MKT/LMT), side(BUY/SELL), quantity, tif(DAY/GTC), price?}.
        IBKR replies with a confirmation prompt (id) that must be confirmed via reply()."""
        d = self._req("POST", f"/iserver/account/{account_id}/orders",
                      json_body={"orders": [order]})
        return d if isinstance(d, list) else [d]

    def reply(self, reply_id: str, confirmed: bool = True) -> list:
        d = self._req("POST", f"/iserver/reply/{reply_id}", json_body={"confirmed": confirmed})
        return d if isinstance(d, list) else [d]

    def live_orders(self) -> dict:
        return self._req("GET", "/iserver/account/orders")

    def cancel_order(self, account_id: str, order_id: str) -> dict:
        return self._req("DELETE", f"/iserver/account/{account_id}/order/{order_id}")
