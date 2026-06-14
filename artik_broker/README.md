# artik_broker

A small web app to analyze one or many stock symbols with the live 100-point engine.

> 📐 **Architecture & sequence diagrams:** see [`ARCHITECTURE.md`](ARCHITECTURE.md) (component flow + 5 sequence diagrams covering analyze, scoring internals, index tabs, portfolio upload).

Two modes:

**1. Symbol mode** — enter symbols (single or **comma-separated**) → ranked table:
Ticker · Sector · Price · **Score · RSI · Status**.

**2. Portfolio mode** — upload one or more broker CSV exports (**e*Trade or Schwab**) →
auto-parses & consolidates holdings across accounts and analyzes every position, adding
**Qty · Cost · Value · P/L** columns plus a totals bar (value / cost / total P/L).

Common to both:
- **Status:** BUY ≥ 75 · HOLD 50–74 · SELL < 50.
- Click **Explain** on any row → full breakdown: the `final = (base − penalties) × multiplier`
  math, per-category bars (Value/Quality/Growth/FinStrength/Technical/Risk), strengths, risks,
  technicals (RSI/MACD/RS rank/MAs), and the trade plan.
- **Download CSV** button exports the current table.

## Run

```bash
cd artik_broker
../artikAPIs/venv/bin/python -m uvicorn app:app --reload --port 8100
# or: ./run.sh
```

Then open **http://localhost:8100**

## How it works

- `app.py` — FastAPI app.
  - `GET /` serves `static/index.html` (vanilla JS single page, no build step).
  - `GET /api/analyze?symbols=NVDA,GOOGL,TSM` → JSON: one row per ticker with the
    full score breakdown embedded (the Explain panel expands client-side, no 2nd call).
  - `POST /api/analyze_portfolio` (multipart `files=`) → parses e*Trade/Schwab CSVs,
    consolidates by symbol across accounts, analyzes each, returns rows + totals.
    (Requires `python-multipart`, already in the artikAPIs venv.)
- Scoring is the shared **`artik-engine`** package at
  `../artikagents/agents/stock_broker_agent/` (`from artik_engine import scoring`,
  `score_ticker_live`) — live yfinance data, no API key. Installed editable into the
  venv (`run.sh` does this automatically; or `pip install -e
  ../artikagents/agents/stock_broker_agent`). The same package backs the
  stock_broker CLI agent, so the engine has one home and two consumers.

## Notes / limits

- ETFs/funds (ARKK, EWY, QQQ, …) return an "engine does not apply" row — the
  fundamental model only scores operating companies.
- Invalid/delisted tickers return a graceful error row.
- Max 40 symbols per request. Prices are live (last close when market is shut).
- Recent IPOs (< ~1 yr history) score unreliably — technicals need history.
