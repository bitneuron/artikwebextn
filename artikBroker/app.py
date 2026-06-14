"""
artikBroker — a small web app to analyze one or many stock symbols.

- Enter symbols (single or comma-separated) → runs the live 100-point engine.
- Results shown in a table (Score / RSI / Status / P-L-agnostic metrics).
- "Explain" per row reveals the full score breakdown behind the recommendation.

Reuses the scoring engine in artikAgents/agents/stock_broker_agent/scoring.py.

Run:
    cd artikBroker
    ../artikAPIs/venv/bin/python -m uvicorn app:app --reload --port 8100
Then open http://localhost:8100
"""
from pathlib import Path
import csv
import io
import json
import os
import re
import sys
import time
import hmac
import hashlib
import warnings
import datetime as dt
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import List

warnings.filterwarnings("ignore")

# The scoring engine is the installed `artik-engine` package
# (artikAgents/agents/stock_broker_agent — `pip install -e` it into this venv).
from artik_engine import scoring  # noqa: E402
import yfinance as yf  # noqa: E402
import alpha_vantage as av  # noqa: E402  (sibling module; key from env, never exposed)
import history_store as hist  # noqa: E402  (server-side search history: S3 on AWS, local folder in dev)
from fastapi import FastAPI, Query, UploadFile, File, Request, Form  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, Response, HTMLResponse, RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

app = FastAPI(title="artikBroker")

HERE = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

# ── Auth gate (login form + signed session cookie + pbkdf2-hashed password) ───
# Enabled when APP_PASSWORD_HASH and APP_SECRET are set (e.g. on AWS). Unset
# locally → open for dev. The raw password is never stored or sent per-request:
# it's typed once into /login (over HTTPS), checked against the hash, then a
# signed HttpOnly+Secure cookie authorises later requests.
APP_PASSWORD_HASH = os.environ.get("APP_PASSWORD_HASH", "")  # pbkdf2_sha256$iters$salt_hex$hash_hex
APP_SECRET = os.environ.get("APP_SECRET", "")
AUTH_ON = bool(APP_PASSWORD_HASH and APP_SECRET)
SESSION_TTL = 7 * 24 * 3600  # 7 days


def _verify_password(pw: str) -> bool:
    try:
        algo, iters, salt, h = APP_PASSWORD_HASH.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), int(iters))
        return hmac.compare_digest(dk.hex(), h)
    except Exception:  # noqa: BLE001
        return False


def _make_token() -> str:
    exp = str(int(time.time()) + SESSION_TTL)
    sig = hmac.new(APP_SECRET.encode(), exp.encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def _valid_token(tok: str) -> bool:
    try:
        exp, sig = tok.rsplit(".", 1)
        good = hmac.new(APP_SECRET.encode(), exp.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, good) and int(exp) > int(time.time())
    except Exception:  # noqa: BLE001
        return False


_LOGIN_HTML = """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>artikBroker — Sign in</title>
<style>body{{margin:0;height:100vh;display:grid;place-items:center;background:#0d1117;color:#e6edf3;
font-family:-apple-system,Segoe UI,Roboto,sans-serif}}form{{background:#161b22;border:1px solid #30363d;
border-radius:12px;padding:28px 26px;width:300px}}h1{{font-size:18px;margin:0 0 4px}}p.sub{{margin:0 0 18px;
color:#8b949e;font-size:13px}}input{{width:100%;box-sizing:border-box;padding:10px 12px;border-radius:8px;
border:1px solid #30363d;background:#0d1117;color:#e6edf3;font-size:14px}}button{{margin-top:12px;width:100%;
padding:10px;border:0;border-radius:8px;background:#1f6feb;color:#fff;font-weight:600;font-size:14px;cursor:pointer}}
.err{{color:#f85149;font-size:13px;margin:10px 0 0}}</style></head>
<body><form method=post action=/login><h1>🔎 artikBroker</h1><p class=sub>Enter the access password.</p>
<input type=password name=password placeholder=Password autofocus required>{err}<button type=submit>Sign in</button></form></body></html>"""


@app.middleware("http")
async def _auth_gate(request: Request, call_next):
    if AUTH_ON:
        path = request.url.path
        public = path.startswith("/login") or path.startswith("/static") or path == "/favicon.ico"
        if not public and not _valid_token(request.cookies.get("session", "")):
            if path.startswith("/api/"):
                return JSONResponse({"error": "unauthorized — please sign in"}, status_code=401)
            return RedirectResponse("/login", status_code=302)
    return await call_next(request)


@app.get("/login")
def login_page():
    return HTMLResponse(_LOGIN_HTML.format(err=""))


@app.post("/login")
def login_submit(password: str = Form("")):
    if AUTH_ON and _verify_password(password):
        resp = RedirectResponse("/", status_code=302)
        resp.set_cookie("session", _make_token(), max_age=SESSION_TTL,
                        httponly=True, secure=True, samesite="lax")
        return resp
    return HTMLResponse(_LOGIN_HTML.format(err='<p class=err>Incorrect password</p>'), status_code=401)


@app.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("session")
    return resp


def _anthropic_key() -> str | None:
    """ANTHROPIC_API_KEY from env (AWS) or the local artikAgents/.env (dev)."""
    k = os.environ.get("ANTHROPIC_API_KEY")
    if k:
        return k
    envf = HERE.parent / "artikAgents" / "agents" / ".env"
    if envf.exists():
        for line in envf.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None

# Saved portfolio snapshots live under Stock_Portfolio/<dated-folder>/combined_portfolio_*.csv
PORTFOLIO_DIR = (
    HERE.parent / "artikAgents" / "agents" / "knowledge_bases" / "Stock_Portfolio"
)

# Treat these as funds the 100-pt fundamental engine can't score meaningfully.
ETFS = {"ARKK", "EWY", "CIBR", "SCHD", "VOO", "QQQ", "SPY", "VTI", "SMH", "IBIT", "DIA", "IWM"}

# Curated index constituents (mega-cap snapshots — stable enough to hardcode).
INDEX_TICKERS = {
    "sp500": [  # S&P 500 top 40 by market cap
        "NVDA", "MSFT", "AAPL", "GOOGL", "AMZN", "META", "AVGO", "TSLA", "BRK-B", "LLY",
        "JPM", "V", "WMT", "MA", "XOM", "ORCL", "UNH", "COST", "HD", "PG",
        "JNJ", "NFLX", "BAC", "ABBV", "KO", "CRM", "CVX", "TMUS", "WFC", "CSCO",
        "MRK", "ACN", "AMD", "PEP", "ADBE", "LIN", "MCD", "GE", "DIS", "IBM",
    ],
    "dow": [  # Dow Jones Industrial Average (30 components)
        "AAPL", "AMGN", "AXP", "AMZN", "BA", "CAT", "CSCO", "CVX", "GS", "HD",
        "HON", "IBM", "JNJ", "JPM", "KO", "MCD", "MMM", "MRK", "MSFT", "NKE",
        "NVDA", "PG", "CRM", "SHW", "TRV", "UNH", "V", "VZ", "WMT", "DIS",
    ],
}
INDEX_LABEL = {"sp500": "S&P 500 (top 40)", "dow": "Dow Jones (30)"}

CATEGORY_MAX = {
    "value": 15, "quality": 22, "growth": 18,
    "fin_str": 13, "technical": 22, "risk": 10,
}


def _status(score: float) -> str:
    return "BUY" if score >= 75 else "HOLD" if score >= 50 else "SELL"


def _fallback_row(t: str, reason: str) -> dict:
    """Graceful error row; if yfinance had no data, try Alpha Vantage for a price."""
    out = {"ticker": t, "error": reason}
    try:
        q = av.global_quote(t)
        gq = q.get("Global Quote") if isinstance(q, dict) else None
        px = gq.get("05. price") if isinstance(gq, dict) else None
        if px:
            out["price"] = round(float(px), 2)
            out["error"] = reason + " — price via Alpha Vantage fallback"
    except Exception:  # noqa: BLE001
        pass
    return out


def analyze_one(ticker: str) -> dict:
    """Run the engine for one ticker and shape it for the UI."""
    t = ticker.strip().upper()
    if not t:
        return None
    if t in ETFS:
        return {"ticker": t, "error": "ETF / fund — the fundamental engine does not apply."}
    try:
        r = scoring.score_ticker_live(t)
    except Exception as e:  # noqa: BLE001
        return _fallback_row(t, f"could not analyze ({type(e).__name__})")

    s = r.get("scores") or {}
    final = s.get("final")
    if final is None:
        return _fallback_row(t, "no data returned")

    tech = r.get("technicals") or {}
    rsi = tech.get("rsi")
    rsi = round(rsi, 1) if isinstance(rsi, (int, float)) and rsi == rsi else None

    return {
        "ticker": t,
        "company": r.get("company"),
        "sector": r.get("sector"),
        "price": round(r["price"], 2) if r.get("price") else None,
        "score": final,
        "rating": s.get("rating"),
        "status": _status(final),
        "rsi": rsi,
        # full breakdown for the Explain panel
        "breakdown": {
            "categories": [
                {"name": k, "label": lbl, "score": s.get(k, 0), "max": CATEGORY_MAX[k]}
                for k, lbl in [
                    ("value", "Value"), ("quality", "Quality"), ("growth", "Growth"),
                    ("fin_str", "Financial Strength"), ("technical", "Technical"),
                    ("risk", "Risk (positive)"),
                ]
            ],
            "base": s.get("base"),
            "penalties": s.get("penalties"),
            "multiplier": s.get("multiplier"),
            "archetype": r.get("archetype"),
            "multiplier_reason": r.get("multiplier_reason"),
            "base_metrics_used": r.get("base_metrics_used") or [],
            "base_metrics_skipped": r.get("base_metrics_skipped") or [],
            "peer_normalized": r.get("peer_normalized", False),
            "peer_explanation": r.get("peer_explanation") or [],
            "final": final,
        },
        "strengths": r.get("strengths") or [],
        "risks": r.get("risks") or [],
        "technicals": {
            "rsi": rsi,
            "macd_state": tech.get("macd_state"),
            "rs_rank": round(tech["rs_rank"], 0) if isinstance(tech.get("rs_rank"), (int, float)) else None,
            "ma20": round(tech["ma20"], 2) if tech.get("ma20") else None,
            "ma50": round(tech["ma50"], 2) if tech.get("ma50") else None,
            "ma200": round(tech["ma200"], 2) if tech.get("ma200") else None,
            "off_52w_hi_pct": round(tech["off_52w_hi_pct"] * 100, 1) if isinstance(tech.get("off_52w_hi_pct"), (int, float)) else None,
        },
        "trade_plan": r.get("trade_plan") or {},
    }


@app.get("/api/analyze")
def api_analyze(symbols: str = Query(..., description="comma-separated tickers")):
    syms, seen = [], set()
    for raw in symbols.replace("\n", ",").split(","):
        t = raw.strip().upper()
        if t and t not in seen:
            seen.add(t)
            syms.append(t)
    if not syms:
        return JSONResponse({"error": "no symbols provided"}, status_code=400)
    if len(syms) > 40:
        return JSONResponse({"error": "max 40 symbols per request"}, status_code=400)

    results = [analyze_one(t) for t in syms]
    results = [r for r in results if r]
    # rank scorable rows by score desc, keep errors at the end
    results.sort(key=lambda r: (r.get("score") is None, -(r.get("score") or 0)))
    return {"count": len(results), "results": results}


# ──────────────────────────────────────────────────────────────────────────────
# AI Search — natural-language stock discovery.
# Claude parses intent into criteria + candidate tickers; the deterministic engine
# produces ALL scores/data (no fabricated numbers). Then filter + rank by Artik Score.
# ──────────────────────────────────────────────────────────────────────────────

_SEARCH_TOOL = {
    "name": "return_search_plan",
    "description": "Return the parsed stock-search plan: a one-line summary, optional "
                   "hard filters to apply against live data, and 12-25 candidate tickers "
                   "most relevant to the query (US-listed operating companies; no ETFs/funds).",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "One sentence describing the interpreted search intent."},
            "filters": {
                "type": "object",
                "description": "Only include keys the query actually implies.",
                "properties": {
                    "sector": {"type": "string", "description": "yfinance sector name to require, e.g. 'Industrials', 'Technology'."},
                    "rsi_max": {"type": "number"},
                    "rsi_min": {"type": "number"},
                    "score_min": {"type": "number"},
                    "score_max": {"type": "number"},
                    "status": {"type": "string", "enum": ["BUY", "HOLD", "SELL"]},
                    "macd_bullish": {"type": "boolean", "description": "true if the query wants a bullish MACD state."},
                },
            },
            "candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string"},
                        "reason": {"type": "string", "description": "Short reason this name matches the SEARCH INTENT (theme/criteria) — not a score."},
                    },
                    "required": ["ticker", "reason"],
                },
            },
        },
        "required": ["summary", "candidates"],
    },
}

_SEARCH_SYSTEM = (
    "You are Artik Broker AI Search, a stock discovery engine. Convert the user's "
    "natural-language query into (1) a one-line intent summary, (2) optional hard filters, "
    "and (3) 12-25 candidate US-listed operating-company tickers most relevant to the intent. "
    "Use correct, real ticker symbols. Prefer liquid, well-known names with strong exposure to "
    "the theme/criteria. Do NOT invent tickers, do NOT include ETFs or funds, and do NOT assign "
    "scores or prices — the scoring engine computes those. Always call return_search_plan."
)


def _score_many(tickers: List[str]) -> List[dict]:
    """Score tickers concurrently via the engine (network-bound -> threads help)."""
    seen, ordered = set(), []
    for t in tickers:
        u = (t or "").strip().upper()
        if u and u not in seen:
            seen.add(u)
            ordered.append(u)
    ordered = ordered[:25]
    with ThreadPoolExecutor(max_workers=8) as ex:
        return list(ex.map(analyze_one, ordered))


def _passes(r: dict, f: dict) -> bool:
    if r.get("error") or r.get("score") is None:
        return False
    if "sector" in f and f["sector"]:
        if (f["sector"] or "").lower() not in (r.get("sector") or "").lower():
            return False
    sc = r.get("score")
    if "score_min" in f and sc < f["score_min"]:
        return False
    if "score_max" in f and sc > f["score_max"]:
        return False
    rsi = r.get("rsi")
    if "rsi_max" in f and (rsi is None or rsi > f["rsi_max"]):
        return False
    if "rsi_min" in f and (rsi is None or rsi < f["rsi_min"]):
        return False
    if "status" in f and f["status"] and r.get("status") != f["status"]:
        return False
    if f.get("macd_bullish"):
        if "bull" not in str((r.get("technicals") or {}).get("macd_state") or "").lower():
            return False
    return True


def _openai_key() -> str | None:
    """OPENAI_API_KEY from env (AWS) or the local artikAgents/.env (dev)."""
    k = os.environ.get("OPENAI_API_KEY")
    if k:
        return k
    envf = HERE.parent / "artikAgents" / "agents" / ".env"
    if envf.exists():
        for line in envf.read_text().splitlines():
            if line.startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _err_detail(e) -> str:
    """Pull the provider's human message out of an SDK exception, if present."""
    body = getattr(e, "body", None)
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict) and err.get("message"):
            return err["message"]
    return str(e)[:200] or type(e).__name__


def _parse_anthropic(query: str, key: str) -> dict | None:
    import anthropic
    client = anthropic.Anthropic(api_key=key)
    msg = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=2000,
        system=_SEARCH_SYSTEM,
        tools=[_SEARCH_TOOL],
        tool_choice={"type": "tool", "name": "return_search_plan"},
        messages=[{"role": "user", "content": query}],
    )
    return next((b.input for b in msg.content if b.type == "tool_use"), None)


def _parse_openai(query: str, key: str) -> dict | None:
    """OpenAI GPT fallback — same structured plan via function calling (GPT-5 API)."""
    from openai import OpenAI
    client = OpenAI(api_key=key)
    resp = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[
            {"role": "system", "content": _SEARCH_SYSTEM},
            {"role": "user", "content": query},
        ],
        tools=[{"type": "function", "function": {
            "name": _SEARCH_TOOL["name"],
            "description": _SEARCH_TOOL["description"],
            "parameters": _SEARCH_TOOL["input_schema"],
        }}],
        tool_choice={"type": "function", "function": {"name": _SEARCH_TOOL["name"]}},
        max_completion_tokens=2000,
        reasoning_effort="minimal",
    )
    calls = resp.choices[0].message.tool_calls
    return json.loads(calls[0].function.arguments) if calls else None


@app.get("/api/search")
def api_search(q: str = Query(..., description="natural-language stock search")):
    query = (q or "").strip()
    if not query:
        return JSONResponse({"error": "empty query"}, status_code=400)

    akey, okey = _anthropic_key(), _openai_key()
    if not akey and not okey:
        return JSONResponse({"error": "AI search unavailable: no ANTHROPIC_API_KEY or OPENAI_API_KEY configured."}, status_code=503)

    # Provider cascade: Claude first; on ANY failure (e.g. low credits) fall back to OpenAI GPT.
    plan, provider, last_err = None, None, None
    if akey:
        try:
            plan, provider = _parse_anthropic(query, akey), "claude"
        except Exception as e:  # noqa: BLE001
            last_err = _err_detail(e)
    if plan is None and okey:
        try:
            plan, provider = _parse_openai(query, okey), "gpt"
        except Exception as e:  # noqa: BLE001
            last_err = _err_detail(e)

    if plan is None:
        return JSONResponse({"error": f"AI search failed: {last_err or 'no provider available'}"}, status_code=502)
    if not plan.get("candidates"):
        return JSONResponse({"error": "could not interpret the query into candidates."}, status_code=422)

    filters = plan.get("filters") or {}
    reasons = {(c.get("ticker") or "").upper(): c.get("reason", "") for c in plan["candidates"]}
    rows = [r for r in _score_many(list(reasons.keys())) if r]

    # Apply hard filters against live engine values; keep scorable rows only.
    matched = [r for r in rows if _passes(r, filters)]
    # If filters eliminate everything, fall back to all scorable candidates (still ranked).
    if not matched:
        matched = [r for r in rows if not r.get("error") and r.get("score") is not None]
    for r in matched:
        r["why"] = reasons.get(r["ticker"], "")
    matched.sort(key=lambda r: -(r.get("score") or 0))

    return {
        "query": query,
        "summary": plan.get("summary", ""),
        "filters": filters,
        "provider": provider,  # "claude" or "gpt" (fallback)
        "count": len(matched),
        "results": matched[:25],
    }


# ──────────────────────────────────────────────────────────────────────────────
# Artik Stock Copilot — AI analyst chat that sits on top of the engine output.
# The Artik Engine output (search results / stock detail passed as context) is the
# single source of truth; the LLM only explains/compares/refines, never invents
# numbers. Provider cascade: Claude first, GPT fallback (same as /api/search).
# ──────────────────────────────────────────────────────────────────────────────
_COPILOT_SYSTEM = """You are Artik Stock Copilot, an AI equity-research analyst embedded inside Artik Broker.
You work alongside the Artik Scoring Engine and help users understand, explore, compare, refine and
discover stocks using Artik Broker's proprietary scoring framework.

You are NOT a generic financial chatbot and NOT a personal investment advisor — you are a copilot for
Artik Broker. Your single source of truth is ALWAYS the Artik Engine output provided as context
(current search results or current stock detail).

MODES
- Search Analysis: when given search results, help the user understand/compare/filter/refine results
  and discover alternatives (e.g. "why did NVDA appear?", "compare the top 3 BUYs", "show only
  Industrials", "find cheaper alternatives").
- Stock Detail: when given one stock's detail, explain why it got its score and BUY/HOLD/SELL, its
  strengths, risks, technicals, fundamentals, signals, trade plan, peer comparison and what-if scenarios.

HOW TO ANSWER
- Be concise. Prefer bullet points, real numbers, and category-score references from the context.
- Cite the Artik figures (score, category scores out of their max, multiplier, archetype, RSI, percentiles).
- For what-if questions, clearly label the analysis as hypothetical and estimate the directional impact;
  never change the actual Artik scores.
- End most answers with 2-3 short suggested follow-up questions when helpful.

SOURCE PRIORITY: current Artik Engine output > current search results/signals/technicals/fundamentals.
Use general financial knowledge ONLY to explain concepts, never to override Artik data.

NEVER invent prices, scores, indicators, fundamentals, or signals. Never hallucinate, never guarantee
future performance, never give personalized investment advice, never recommend specific trades.

MISSING DATA: if something is not in the provided context, say
"I do not see that information in the current Artik Engine output." Do not guess."""


def _copilot_context_block(mode: str, context: dict) -> str:
    label = "CURRENT STOCK DETAIL" if mode == "stock" else "CURRENT SEARCH RESULTS"
    try:
        blob = json.dumps(context, default=str)[:14000]
    except Exception:  # noqa: BLE001
        blob = "{}"
    return (f"{label} — Artik Engine output (your single source of truth; do not invent anything "
            f"beyond this):\n```json\n{blob}\n```")


def _copilot_anthropic(messages, sys_text, key):
    import anthropic
    client = anthropic.Anthropic(api_key=key)
    msg = client.messages.create(model="claude-opus-4-8", max_tokens=1200,
                                 system=sys_text, messages=messages)
    return "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text").strip()


def _copilot_openai(messages, sys_text, key):
    from openai import OpenAI
    client = OpenAI(api_key=key)
    resp = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[{"role": "system", "content": sys_text}] + messages,
        max_completion_tokens=1200, reasoning_effort="minimal")
    return (resp.choices[0].message.content or "").strip()


@app.post("/api/copilot")
async def api_copilot(request: Request):
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    raw = body.get("messages") or []
    if not raw:
        return JSONResponse({"error": "no messages"}, status_code=400)
    # keep the last 12 turns; coerce to clean user/assistant text
    conv = [{"role": ("assistant" if m.get("role") == "assistant" else "user"),
             "content": str(m.get("content", ""))[:4000]} for m in raw][-12:]
    if conv[0]["role"] != "user":              # Anthropic requires a leading user turn
        conv = conv[1:]
    if not conv:
        return JSONResponse({"error": "no user message"}, status_code=400)
    mode = "stock" if body.get("mode") == "stock" else "search"
    sys_text = _COPILOT_SYSTEM + "\n\n" + _copilot_context_block(mode, body.get("context") or {})

    akey, okey = _anthropic_key(), _openai_key()
    if not akey and not okey:
        return JSONResponse({"error": "Copilot unavailable: no ANTHROPIC_API_KEY or OPENAI_API_KEY configured."}, status_code=503)
    reply, provider, last_err = None, None, None
    if akey:
        try:
            reply, provider = _copilot_anthropic(conv, sys_text, akey), "claude"
        except Exception as e:  # noqa: BLE001
            last_err = _err_detail(e)
    if reply is None and okey:
        try:
            reply, provider = _copilot_openai(conv, sys_text, okey), "gpt"
        except Exception as e:  # noqa: BLE001
            last_err = _err_detail(e)
    if not reply:
        return JSONResponse({"error": f"Copilot failed: {last_err or 'no provider available'}"}, status_code=502)
    return {"provider": provider, "reply": reply}


# ──────────────────────────────────────────────────────────────────────────────
# Alpha Vantage enrichment — on-demand single-ticker Bollinger Bands + fundamentals.
# Fired only when a user clicks "Explain → Load Alpha Vantage" (respects the free
# 25/day budget); cached once per ticker per day. yfinance stays the engine's source.
# ──────────────────────────────────────────────────────────────────────────────

_FUND_FIELDS = [
    ("Sector", "Sector"), ("Industry", "Industry"), ("MarketCapitalization", "Market cap"),
    ("PERatio", "P/E"), ("ForwardPE", "Forward P/E"), ("PEGRatio", "PEG"),
    ("PriceToSalesRatioTTM", "P/S"), ("ProfitMargin", "Profit margin"),
    ("ReturnOnEquityTTM", "ROE"), ("ReturnOnAssetsTTM", "ROA"),
    ("RevenueTTM", "Revenue TTM"), ("EPS", "EPS"), ("DividendYield", "Div yield"),
    ("Beta", "Beta"), ("AnalystTargetPrice", "Analyst target"),
]


@app.get("/api/enrich/{ticker}")
def api_enrich(ticker: str):
    t = ticker.strip().upper()
    if not t:
        return JSONResponse({"success": False, "error": "no ticker"}, status_code=400)
    if not av.is_configured():
        return {"success": False, "error": "ALPHA_VANTAGE_API_KEY is not configured"}

    today = dt.date.today().isoformat()
    cache_dir = HERE / "cache"
    cache_path = cache_dir / f"enrich_{t}_{today}.json"
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text())
        except Exception:  # noqa: BLE001
            pass

    # Current price from yfinance (free) for the Bollinger position comparison
    price = None
    try:
        fi = yf.Ticker(t).fast_info
        price = getattr(fi, "last_price", None)
    except Exception:  # noqa: BLE001
        price = None

    bb = {}
    bands = av.bbands(t)
    ta = bands.get("Technical Analysis: BBANDS") if isinstance(bands, dict) else None
    if ta:
        latest = sorted(ta.keys())[-1]
        v = ta[latest]
        up, mid, lo = float(v["Real Upper Band"]), float(v["Real Middle Band"]), float(v["Real Lower Band"])
        bb = {"date": latest, "upper": round(up, 2), "middle": round(mid, 2), "lower": round(lo, 2)}
        if price is not None:
            bb["price"] = round(float(price), 2)
            rng = up - lo
            pct = ((price - lo) / rng * 100) if rng else None
            bb["position_pct"] = round(pct) if pct is not None else None
            bb["position_label"] = (
                "above upper band — overbought" if price > up else
                "below lower band — oversold" if price < lo else
                "upper half of band" if (pct is not None and pct >= 50) else "lower half of band"
            )

    fund = {}
    ov = av.overview(t)
    if isinstance(ov, dict) and ov.get("Symbol"):
        for key, label in _FUND_FIELDS:
            val = ov.get(key)
            if val and val not in ("None", "0", "-", "0.0"):
                fund[label] = val

    if not bb and not fund:
        err = (bands.get("error") if isinstance(bands, dict) else None) or \
              (ov.get("error") if isinstance(ov, dict) else None) or "Alpha Vantage data unavailable"
        return {"success": False, "error": err}

    out = {"success": True, "ticker": t, "bollinger": bb, "fundamentals": fund}
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(out))
    except Exception:  # noqa: BLE001
        pass
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Portfolio-upload mode — parse broker CSVs (e*Trade + Schwab) and analyze holdings
# ──────────────────────────────────────────────────────────────────────────────

def _num(s) -> float:
    if s is None:
        return 0.0
    s = str(s).replace("$", "").replace(",", "").replace("%", "").strip().strip('"')
    if s in ("", "-", "--", "N/A"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_portfolio_csv(text: str, acc: dict) -> None:
    """Auto-detect e*Trade or Schwab export and accumulate {sym:{qty,cost}} into acc."""
    lines = text.splitlines()

    # e*Trade: a header row beginning "Symbol,Last Price"
    etr = next((i for i, l in enumerate(lines) if l.startswith("Symbol,Last Price")), None)
    if etr is not None:
        hdr = next(csv.reader([lines[etr]]))
        for row in csv.reader(lines[etr + 1:]):
            if not row or not row[0]:
                continue
            s = row[0].strip()
            if not re.match(r"^[A-Z]{1,5}$", s) or s in ("TOTAL", "Symbol"):
                continue
            d = dict(zip(hdr, row))
            q = _num(d.get("Qty #"))
            acc[s]["qty"] += q
            acc[s]["cost"] += q * _num(d.get("Price Paid $"))
        return

    # Schwab: quoted CSV; a header row whose first cell == "Symbol"
    rows = list(csv.reader(lines))
    hd = None
    for r in rows:
        if r and r[0] == "Symbol":
            hd = r
            continue
        if hd and r and re.match(r"^[A-Z\.]{1,6}$", r[0].strip()):
            d = dict(zip(hd, r))
            s = r[0].strip()
            acc[s]["qty"] += _num(d.get("Qty (Quantity)"))
            acc[s]["cost"] += _num(d.get("Cost Basis"))


def _live_price(ticker: str):
    try:
        info = yf.Ticker(ticker).info or {}
        return info.get("currentPrice") or info.get("regularMarketPrice") \
            or info.get("regularMarketPreviousClose")
    except Exception:  # noqa: BLE001
        return None


@app.post("/api/analyze_portfolio")
async def api_analyze_portfolio(files: List[UploadFile] = File(...)):
    acc = defaultdict(lambda: {"qty": 0.0, "cost": 0.0})
    parsed_files = []
    for f in files:
        raw = (await f.read()).decode("utf-8", errors="replace")
        before = len(acc)
        parse_portfolio_csv(raw, acc)
        parsed_files.append({"name": f.filename, "symbols": len(acc) - before})

    acc = {k: v for k, v in acc.items() if v["qty"] > 0}
    if not acc:
        return JSONResponse(
            {"error": "No holdings parsed. Expecting e*Trade or Schwab CSV exports."},
            status_code=400,
        )

    results = []
    tot_cost = tot_val = 0.0
    for sym, h in acc.items():
        qty, cost = h["qty"], h["cost"]
        row = analyze_one(sym) or {"ticker": sym, "error": "no data"}
        price = row.get("price") or _live_price(sym)
        value = qty * price if price else 0.0
        pl = value - cost
        row.update({
            "qty": round(qty, 4),
            "cost_basis": round(cost, 2),
            "price": round(price, 2) if price else None,
            "value": round(value, 2),
            "pl": round(pl, 2),
            "pl_pct": round(pl / cost * 100, 1) if cost else None,
        })
        results.append(row)
        tot_cost += cost
        tot_val += value

    results.sort(key=lambda r: -r.get("value", 0))
    tot_pl = tot_val - tot_cost
    return {
        "count": len(results),
        "results": results,
        "files": parsed_files,
        "totals": {
            "cost": round(tot_cost, 2),
            "value": round(tot_val, 2),
            "pl": round(tot_pl, 2),
            "pl_pct": round(tot_pl / tot_cost * 100, 1) if tot_cost else None,
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# Saved portfolio snapshots — the "Portfolio" tab (one entry per dated run)
# ──────────────────────────────────────────────────────────────────────────────

def _list_portfolio_snapshots() -> list:
    """All saved combined_portfolio_*.csv files, newest date first."""
    out = []
    if PORTFOLIO_DIR.is_dir():
        for csv_path in PORTFOLIO_DIR.glob("*/combined_portfolio_*.csv"):
            m = re.search(r"(\d{4}-\d{2}-\d{2})", csv_path.name)
            date = m.group(1) if m else csv_path.parent.name
            out.append({
                "date": date,
                "folder": csv_path.parent.name,
                "file": str(csv_path.relative_to(PORTFOLIO_DIR)),
            })
    out.sort(key=lambda x: x["date"], reverse=True)
    return out


@app.get("/api/portfolio/dates")
def api_portfolio_dates():
    return {"snapshots": _list_portfolio_snapshots()}


@app.get("/api/portfolio")
def api_portfolio(date: str = Query(None), file: str = Query(None)):
    snaps = _list_portfolio_snapshots()
    if not snaps:
        return JSONResponse({"error": "No saved portfolio snapshots found."}, status_code=404)
    chosen = None
    if file:
        chosen = next((s for s in snaps if s["file"] == file), None)
    elif date:
        chosen = next((s for s in snaps if s["date"] == date), None)
    chosen = chosen or snaps[0]

    path = PORTFOLIO_DIR / chosen["file"]
    rows, totals, as_of = [], None, None
    reader = csv.DictReader(path.read_text().splitlines())
    for r in reader:
        tag = (r.get("#") or "").strip()
        if tag == "TOTAL":
            totals = {
                "qty": r.get("Qty"), "cost": r.get("Cost_Basis"),
                "value": r.get("Value"), "pl": r.get("PL_$"), "pl_pct": r.get("PL_%"),
            }
            continue
        if tag == "AS_OF":
            as_of = r.get("Ticker")
            continue
        if not tag or not (r.get("Ticker") or "").strip():
            continue
        rows.append({
            "n": tag, "ticker": r.get("Ticker"), "qty": r.get("Qty"),
            "archetype": r.get("Archetype", ""),
            "cost_basis": r.get("Cost_Basis"), "price": r.get("Price"),
            "value": r.get("Value"), "score": r.get("Score"), "rating": r.get("Rating"),
            "rsi": r.get("RSI"), "status": r.get("Status"),
            "pl": r.get("PL_$"), "pl_pct": r.get("PL_%"),
        })
    return {
        "date": chosen["date"], "folder": chosen["folder"], "file": chosen["file"],
        "as_of": as_of, "count": len(rows), "rows": rows, "totals": totals,
    }


@app.get("/api/portfolio/refresh")
def api_portfolio_refresh(date: str = Query(None), file: str = Query(None)):
    """Re-score a saved snapshot's holdings against LIVE data.

    Share counts + cost basis come from the broker export (only as fresh as the
    snapshot); price, score, RSI, status, archetype, value and P/L are recomputed
    live via the engine. Returns the same shape as /api/portfolio so the same
    renderer can display it.
    """
    snaps = _list_portfolio_snapshots()
    if not snaps:
        return JSONResponse({"error": "No saved portfolio snapshots found."}, status_code=404)
    chosen = None
    if file:
        chosen = next((s for s in snaps if s["file"] == file), None)
    elif date:
        chosen = next((s for s in snaps if s["date"] == date), None)
    chosen = chosen or snaps[0]

    # Holdings (ticker -> qty, cost_basis) from the snapshot CSV.
    path = PORTFOLIO_DIR / chosen["file"]
    holdings = []  # preserve original order
    for r in csv.DictReader(path.read_text().splitlines()):
        tag = (r.get("#") or "").strip()
        if tag in ("TOTAL", "AS_OF") or not tag:
            continue
        t = (r.get("Ticker") or "").strip().upper()
        if not t:
            continue
        holdings.append({"ticker": t, "qty": _num(r.get("Qty")), "cost_basis": _num(r.get("Cost_Basis"))})

    if not holdings:
        return JSONResponse({"error": "snapshot has no holdings to refresh."}, status_code=404)

    # Score every holding live (NOT _score_many — that caps at 25 for AI Search).
    tickers = list(dict.fromkeys(h["ticker"] for h in holdings))
    with ThreadPoolExecutor(max_workers=8) as ex:
        scored = {r["ticker"]: r for r in ex.map(analyze_one, tickers) if r}

    rows, t_cost, t_val, t_pl = [], 0.0, 0.0, 0.0
    for i, h in enumerate(holdings, 1):
        t, qty, cost = h["ticker"], h["qty"], h["cost_basis"]
        sr = scored.get(t) or {}
        price = sr.get("price")
        if price is None:  # ETFs / unscored — still price the position for the totals
            lp = _live_price(t)
            price = round(lp, 2) if lp else None
        value = round(qty * price, 2) if (qty and price is not None) else None
        pl = round(value - cost, 2) if (value is not None and cost) else None
        pl_pct = round(pl / cost * 100, 2) if (pl is not None and cost) else None
        t_cost += cost or 0
        t_val += value or 0
        t_pl += pl or 0
        rows.append({
            "n": i, "ticker": t, "qty": qty,
            "archetype": (sr.get("breakdown") or {}).get("archetype", "") or "",
            "cost_basis": cost, "price": price, "value": value,
            "score": sr.get("score"), "rating": sr.get("rating"),
            "rsi": sr.get("rsi"), "status": sr.get("status"),
            "pl": pl, "pl_pct": pl_pct,
            "error": sr.get("error"),
        })

    totals = {
        "qty": None, "cost": round(t_cost, 2), "value": round(t_val, 2),
        "pl": round(t_pl, 2), "pl_pct": round(t_pl / t_cost * 100, 2) if t_cost else None,
    }
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    return {
        "date": chosen["date"], "folder": chosen["folder"], "file": chosen["file"],
        "as_of": f"Live refresh {now}", "refreshed": True,
        "count": len(rows), "rows": rows, "totals": totals,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Search history — persisted server-side (S3 on AWS, local folder in dev) so it
# survives browser close / redeploys and is shared across devices.
# ──────────────────────────────────────────────────────────────────────────────
@app.post("/api/history")
async def api_history_save(request: Request):
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    if not (body.get("query") or "").strip():
        return JSONResponse({"error": "missing query"}, status_code=400)
    try:
        return hist.save(body)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"could not save history: {_err_detail(e)}"}, status_code=500)


@app.get("/api/history")
def api_history_list():
    try:
        return {"backend": hist.backend(), "searches": hist.list_meta()}
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"could not list history: {_err_detail(e)}"}, status_code=500)


@app.get("/api/history/{eid}")
def api_history_get(eid: str):
    e = hist.get(eid)
    if not e:
        return JSONResponse({"error": "not found"}, status_code=404)
    return e


@app.post("/api/history/delete")
async def api_history_delete_bulk(request: Request):
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    ids = body.get("ids") or []
    if not isinstance(ids, list) or not ids:
        return JSONResponse({"error": "no ids"}, status_code=400)
    return {"ok": True, "deleted": hist.delete_many(ids)}


@app.delete("/api/history/{eid}")
def api_history_delete(eid: str):
    hist.delete(eid)
    return {"ok": True}


@app.delete("/api/history")
def api_history_clear():
    hist.clear()
    return {"ok": True}


# ──────────────────────────────────────────────────────────────────────────────
# Index tabs — S&P 500 (top 40) and Dow (30), scored live & cached daily
# ──────────────────────────────────────────────────────────────────────────────
_INDEX_CACHE_DIR = HERE / "cache"


@app.get("/api/index/{name}")
def api_index(name: str, refresh: bool = False):
    name = name.lower()
    if name not in INDEX_TICKERS:
        return JSONResponse({"error": f"unknown index '{name}'"}, status_code=404)
    today = dt.date.today().isoformat()
    cache_path = _INDEX_CACHE_DIR / f"index_{name}_{today}.json"
    if cache_path.exists() and not refresh:
        try:
            return json.loads(cache_path.read_text())
        except Exception:
            pass
    results = [analyze_one(t) for t in INDEX_TICKERS[name]]
    results = [r for r in results if r]
    results.sort(key=lambda r: (r.get("score") is None, -(r.get("score") or 0)))
    payload = {"index": name, "label": INDEX_LABEL[name], "as_of": today,
               "count": len(results), "results": results}
    try:
        _INDEX_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload))
    except Exception:
        pass
    return payload


@app.get("/")
def index():
    return FileResponse(HERE / "static" / "index.html")
