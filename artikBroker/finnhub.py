"""Finnhub API client — INTELLIGENCE provider only.

Finnhub is used *exclusively* for intelligence / event-driven data (company news &
sentiment, analyst recommendation trends, insider transactions & sentiment, institutional
ownership, SEC filings, earnings events, IPO calendar, ESG). It is NOT used for quotes,
prices, financial statements, ratios, valuation, or technical indicators — those stay with
Yahoo Finance, Alpha Vantage, and Financial Modeling Prep.

Base: https://finnhub.io/api/v1 . Auth via the FINNHUB_API_KEY environment variable
(query `?token=` + `X-Finnhub-Token` header where supported). The key is NEVER logged:
errors carry only the endpoint path and any text is scrubbed/masked. Responses are cached
(TTL) to reduce API usage; if Finnhub is unavailable the caller degrades gracefully.
"""
from __future__ import annotations

import datetime as _dt
import os
import time

try:  # requests is in the Broker image; guarded so unit tests import without it
    import requests
except Exception:  # noqa: BLE001
    requests = None  # type: ignore

BASE_URL = "https://finnhub.io/api/v1"
_CACHE: dict[str, tuple[float, object]] = {}
_CACHE_TTL = float(os.environ.get("FINNHUB_CACHE_TTL", "900"))   # 15 min default


def _env_key() -> str:
    return os.environ.get("FINNHUB_API_KEY", "")


def mask_key(k: str) -> str:
    if not k:
        return "(unset)"
    return f"{k[:4]}…{k[-2:]}" if len(k) > 8 else "…"


def _scrub(text: str, key: str) -> str:
    return text.replace(key, mask_key(key)) if (key and text) else text


class FinnhubError(Exception):
    pass


def _ago(days: int) -> str:
    return (_dt.date.today() - _dt.timedelta(days=days)).isoformat()


def _today() -> str:
    return _dt.date.today().isoformat()


class FinnhubClient:
    def __init__(self, key: str | None = None, base: str | None = None,
                 timeout: float = 12.0, retries: int = 2):
        self.key = key if key is not None else _env_key()
        self.base = base or os.environ.get("FINNHUB_BASE_URL", BASE_URL)
        self.timeout = timeout
        self.retries = retries

    @property
    def configured(self) -> bool:
        return bool(self.key)

    def _get(self, path: str, params: dict | None = None, cache: bool = True):
        if not self.key:
            raise FinnhubError("FINNHUB_API_KEY is not configured")
        if requests is None:
            raise FinnhubError("the 'requests' library is not available")
        ck = f"{path}?{sorted((params or {}).items())}"
        if cache and ck in _CACHE:
            ts, val = _CACHE[ck]
            if time.time() - ts < _CACHE_TTL:
                return val
        url = f"{self.base}{path}"
        q = dict(params or {})
        q["token"] = self.key
        headers = {"X-Finnhub-Token": self.key}
        last = None
        for attempt in range(self.retries + 1):
            try:
                r = requests.get(url, params=q, headers=headers, timeout=self.timeout)
                if r.status_code == 200:
                    val = r.json()
                    if cache:
                        _CACHE[ck] = (time.time(), val)
                    return val
                if r.status_code == 429 and attempt < self.retries:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                last = FinnhubError(f"Finnhub {path} HTTP {r.status_code}: {_scrub(r.text[:150], self.key)}")
            except Exception as e:  # noqa: BLE001
                last = FinnhubError(f"Finnhub {path} error: {_scrub(str(e), self.key)}")
            if attempt < self.retries:
                time.sleep(0.8 * (attempt + 1))
        raise last or FinnhubError(f"Finnhub {path} failed")

    # ── intelligence datasets ──────────────────────────────────────────────────
    def company_news(self, s, days=14):
        return self._get("/company-news", {"symbol": s, "from": _ago(days), "to": _today()})

    def news_sentiment(self, s):
        return self._get("/news-sentiment", {"symbol": s})

    def recommendation_trends(self, s):
        return self._get("/stock/recommendation", {"symbol": s})

    def insider_transactions(self, s):
        return self._get("/stock/insider-transactions", {"symbol": s})

    def insider_sentiment(self, s, days=180):
        return self._get("/stock/insider-sentiment", {"symbol": s, "from": _ago(days), "to": _today()})

    def fund_ownership(self, s, limit=20):
        return self._get("/stock/fund-ownership", {"symbol": s, "limit": limit})

    def filings(self, s):
        return self._get("/stock/filings", {"symbol": s})

    def earnings_surprises(self, s, limit=8):
        return self._get("/stock/earnings", {"symbol": s, "limit": limit})

    def earnings_calendar(self, s, days=90):
        return self._get("/calendar/earnings", {"symbol": s, "from": _today(), "to": _ago(-days)})

    def ipo_calendar(self, days=30):
        return self._get("/calendar/ipo", {"from": _today(), "to": _ago(-days)})

    def esg(self, s):
        return self._get("/stock/esg", {"symbol": s})

    # ── bundle: fetch all intelligence, resiliently (one failure ≠ total) ───────
    def bundle(self, symbol: str) -> dict:
        datasets = {
            "company_news": lambda: self.company_news(symbol),
            "news_sentiment": lambda: self.news_sentiment(symbol),
            "recommendations": lambda: self.recommendation_trends(symbol),
            "insider_transactions": lambda: self.insider_transactions(symbol),
            "insider_sentiment": lambda: self.insider_sentiment(symbol),
            "fund_ownership": lambda: self.fund_ownership(symbol),
            "filings": lambda: self.filings(symbol),
            "earnings": lambda: self.earnings_surprises(symbol),
            "earnings_calendar": lambda: self.earnings_calendar(symbol),
            "esg": lambda: self.esg(symbol),
        }
        data, errors = {}, {}
        for name, fn in datasets.items():
            try:
                data[name] = fn()
            except Exception as e:  # noqa: BLE001
                errors[name] = str(e)
        return {"data": data, "errors": errors, "ok": bool(data)}
