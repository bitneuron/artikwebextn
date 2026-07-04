"""Financial Modeling Prep (FMP) API client — third stock-data provider.

Base: https://financialmodelingprep.com/stable . Auth via the FMP_API_KEY environment
variable (query `?apikey=` — FMP's standard — plus an `apikey` header where supported).
The key is NEVER logged: error messages carry only the endpoint path, and any text that
might contain the key is masked.

Yahoo Finance → Alpha Vantage → **FMP** → Claude/OpenAI. FMP is additive: if it fails, the
pipeline continues with whatever Yahoo/Alpha Vantage returned.
"""
from __future__ import annotations

import os
import time

try:  # requests is in the Broker image; guarded so unit tests import without it
    import requests
except Exception:  # noqa: BLE001
    requests = None  # type: ignore

BASE_URL = "https://financialmodelingprep.com/stable"


def _env_key() -> str:
    return os.environ.get("FMP_API_KEY", "")


def mask_key(k: str) -> str:
    """Short, non-reversible representation for logs (never the full key)."""
    if not k:
        return "(unset)"
    return f"{k[:4]}…{k[-2:]}" if len(k) > 8 else "…"


def _scrub(text: str, key: str) -> str:
    """Remove the API key from any error text before it can be surfaced/logged."""
    if key and text:
        return text.replace(key, mask_key(key))
    return text


class FMPError(Exception):
    pass


class FMPClient:
    def __init__(self, key: str | None = None, base: str | None = None,
                 timeout: float = 12.0, retries: int = 2):
        self.key = key if key is not None else _env_key()
        self.base = base or os.environ.get("FMP_BASE_URL", BASE_URL)
        self.timeout = timeout
        self.retries = retries

    @property
    def configured(self) -> bool:
        return bool(self.key)

    def _get(self, path: str, params: dict | None = None):
        if not self.key:
            raise FMPError("FMP_API_KEY is not configured")
        if requests is None:
            raise FMPError("the 'requests' library is not available")
        url = f"{self.base}{path}"
        q = dict(params or {})
        q["apikey"] = self.key                       # FMP standard: query param
        headers = {"apikey": self.key}               # header auth where supported
        last = None
        for attempt in range(self.retries + 1):
            try:
                r = requests.get(url, params=q, headers=headers, timeout=self.timeout)
                if r.status_code == 200:
                    return r.json()
                if r.status_code == 429 and attempt < self.retries:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                # NOTE: `path` only — never the full URL (which carries ?apikey=).
                last = FMPError(f"FMP {path} HTTP {r.status_code}: {_scrub(r.text[:150], self.key)}")
            except Exception as e:  # noqa: BLE001
                last = FMPError(f"FMP {path} error: {_scrub(str(e), self.key)}")
            if attempt < self.retries:
                time.sleep(0.8 * (attempt + 1))
        raise last or FMPError(f"FMP {path} failed")

    # ── datasets ───────────────────────────────────────────────────────────────
    def profile(self, s):             return self._get("/profile", {"symbol": s})
    def quote(self, s):               return self._get("/quote", {"symbol": s})
    def income_statement(self, s, limit=2):   return self._get("/income-statement", {"symbol": s, "limit": limit})
    def balance_sheet(self, s, limit=2):      return self._get("/balance-sheet-statement", {"symbol": s, "limit": limit})
    def cash_flow(self, s, limit=2):          return self._get("/cash-flow-statement", {"symbol": s, "limit": limit})
    def ratios(self, s, limit=1):     return self._get("/ratios", {"symbol": s, "limit": limit})
    def key_metrics(self, s, limit=1):        return self._get("/key-metrics", {"symbol": s, "limit": limit})
    def enterprise_values(self, s, limit=1):  return self._get("/enterprise-values", {"symbol": s, "limit": limit})
    def analyst_estimates(self, s, limit=1):  return self._get("/analyst-estimates", {"symbol": s, "limit": limit})
    def dividends(self, s, limit=5):  return self._get("/dividends", {"symbol": s, "limit": limit})
    def splits(self, s, limit=5):     return self._get("/splits", {"symbol": s, "limit": limit})
    def earnings(self, s, limit=4):   return self._get("/earnings", {"symbol": s, "limit": limit})
    def sec_filings(self, s, limit=5):        return self._get("/sec-filings-search/symbol", {"symbol": s, "limit": limit})

    # ── bundle: fetch everything, resiliently (one failure ≠ total failure) ─────
    def bundle(self, symbol: str) -> dict:
        """Fetch all datasets for a ticker. Returns {data:{...}, errors:{...}, ok:bool}."""
        datasets = {
            "profile": self.profile, "quote": self.quote,
            "income_statement": self.income_statement, "balance_sheet": self.balance_sheet,
            "cash_flow": self.cash_flow, "ratios": self.ratios, "key_metrics": self.key_metrics,
            "enterprise_values": self.enterprise_values, "analyst_estimates": self.analyst_estimates,
            "dividends": self.dividends, "splits": self.splits, "earnings": self.earnings,
            "sec_filings": self.sec_filings,
        }
        data, errors = {}, {}
        for name, fn in datasets.items():
            try:
                data[name] = fn(symbol)
            except Exception as e:  # noqa: BLE001 — per-dataset resilience
                errors[name] = str(e)
        return {"data": data, "errors": errors, "ok": bool(data)}
