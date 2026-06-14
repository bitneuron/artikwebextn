"""Alpha Vantage client.

The API key is read from the environment variable ALPHA_VANTAGE_API_KEY
(never hardcoded). The key is never logged, returned, or placed in error
messages — request URLs that embed the key are never surfaced.

Endpoints: RSI, MACD, SMA, EMA, BBANDS (Bollinger Bands), OVERVIEW.
"""
from __future__ import annotations

import os
from pathlib import Path

import requests

BASE_URL = "https://www.alphavantage.co/query"
_MISSING = {"success": False, "error": "ALPHA_VANTAGE_API_KEY is not configured"}


def _api_key() -> str | None:
    """ALPHA_VANTAGE_API_KEY from env (prod) or the local artikAgents/.env (dev)."""
    k = os.getenv("ALPHA_VANTAGE_API_KEY")
    if k:
        return k
    envf = Path(__file__).resolve().parent.parent / "artikAgents" / "agents" / ".env"
    if envf.exists():
        for line in envf.read_text().splitlines():
            if line.startswith("ALPHA_VANTAGE_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _request(params: dict) -> dict:
    """Call Alpha Vantage. Returns the raw JSON on success, or a {success:false,...}
    envelope. The API key is appended here and never echoed back."""
    key = _api_key()
    if not key:
        return dict(_MISSING)
    try:
        resp = requests.get(BASE_URL, params={**params, "apikey": key}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:  # noqa: BLE001 — scrub: never include the URL (it carries the key)
        return {"success": False, "error": f"Alpha Vantage request failed ({type(e).__name__})"}
    # Alpha Vantage signals problems in the body, not the HTTP status:
    if isinstance(data, dict):
        if "Error Message" in data:
            return {"success": False, "error": data["Error Message"]}
        if "Note" in data:        # rate limit
            return {"success": False, "error": data["Note"]}
        if "Information" in data:  # key/plan limit notice
            return {"success": False, "error": data["Information"]}
    return data


# ── Technical indicators ──────────────────────────────────────────────────────
def rsi(symbol: str, interval: str = "daily", time_period: int = 14, series_type: str = "close") -> dict:
    return _request({"function": "RSI", "symbol": symbol, "interval": interval,
                     "time_period": time_period, "series_type": series_type})


def macd(symbol: str, interval: str = "daily", series_type: str = "close") -> dict:
    return _request({"function": "MACD", "symbol": symbol, "interval": interval,
                     "series_type": series_type})


def sma(symbol: str, interval: str = "daily", time_period: int = 50, series_type: str = "close") -> dict:
    return _request({"function": "SMA", "symbol": symbol, "interval": interval,
                     "time_period": time_period, "series_type": series_type})


def ema(symbol: str, interval: str = "daily", time_period: int = 50, series_type: str = "close") -> dict:
    return _request({"function": "EMA", "symbol": symbol, "interval": interval,
                     "time_period": time_period, "series_type": series_type})


def bbands(symbol: str, interval: str = "daily", time_period: int = 20, series_type: str = "close") -> dict:
    return _request({"function": "BBANDS", "symbol": symbol, "interval": interval,
                     "time_period": time_period, "series_type": series_type})


# ── Fundamentals / quote ──────────────────────────────────────────────────────
def overview(symbol: str) -> dict:
    return _request({"function": "OVERVIEW", "symbol": symbol})


def global_quote(symbol: str) -> dict:
    """Latest price quote — used as a fallback when yfinance has no data."""
    return _request({"function": "GLOBAL_QUOTE", "symbol": symbol})


def is_configured() -> bool:
    return _api_key() is not None
