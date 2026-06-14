"""
artik_broker — a small web app to analyze one or many stock symbols.

- Enter symbols (single or comma-separated) → runs the live 100-point engine.
- Results shown in a table (Score / RSI / Status / P-L-agnostic metrics).
- "Explain" per row reveals the full score breakdown behind the recommendation.

Reuses the scoring engine in artikagents/agents/stock_broker_agent/scoring.py.

Run:
    cd artik_broker
    ../artikAPIs/venv/bin/python -m uvicorn app:app --reload --port 8100
Then open http://localhost:8100
"""
from pathlib import Path
import csv
import io
import json
import re
import sys
import warnings
import datetime as dt
from collections import defaultdict
from typing import List

warnings.filterwarnings("ignore")

# Make the scoring engine importable.
SCORING_DIR = (
    Path(__file__).resolve().parent.parent
    / "artikagents" / "agents" / "stock_broker_agent"
)
sys.path.insert(0, str(SCORING_DIR))

import scoring  # noqa: E402
import yfinance as yf  # noqa: E402
from fastapi import FastAPI, Query, UploadFile, File  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

app = FastAPI(title="artik_broker")

HERE = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

# Saved portfolio snapshots live under Stock_Portfolio/<dated-folder>/combined_portfolio_*.csv
PORTFOLIO_DIR = (
    HERE.parent / "artikagents" / "agents" / "knowledge_bases" / "Stock_Portfolio"
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
        return {"ticker": t, "error": f"could not analyze ({type(e).__name__})"}

    s = r.get("scores") or {}
    final = s.get("final")
    if final is None:
        return {"ticker": t, "error": "no data returned"}

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
