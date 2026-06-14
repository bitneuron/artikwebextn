# artik_broker web app (built 2026-06-13)

A standalone web app to analyze one/many stock symbols and show BUY/HOLD/SELL with an Explain breakdown.

## Location & run
- Folder: `artik_broker/` (project root, sibling to artikAPIs/artikagents).
- Run: `cd artik_broker && ./run.sh`  (or `../artikAPIs/venv/bin/python -m uvicorn app:app --reload --port 8100`)
- Open: **http://localhost:8100**
- Uses the **artikAPIs venv** (has fastapi/uvicorn/yfinance). No API key needed.

## What it does
- **Symbol mode:** text box → comma-separated symbols → ranked table (Ticker · Sector · Price · Score · RSI · Status).
- **Portfolio mode:** upload e*Trade/Schwab CSV export(s) → parses+consolidates holdings, analyzes each,
  adds Qty · Cost · Value · P/L columns + totals bar. (Reconciled exactly with the manual June-13 run; figures in the gitignored portfolio snapshot.)
- **Status:** BUY ≥75 · HOLD 50–74 · SELL <50.
- **Explain** button per row expands the full breakdown: `final=(base−penalties)×multiplier`,
  6 category bars (Value/Quality/Growth/FinStrength/Technical/Risk), strengths, risks, technicals, trade plan.
- **Download CSV** button exports the current table (symbol or portfolio).
- **Tabs:** Analyze · Portfolio (saved snapshots by date, sortable + ticker/status search + per-row Explain; shows Archetype col) · **S&P 500** (top 40 by mkt cap) · **DOW** (30). Index tabs hit `GET /api/index/{sp500|dow}` which scores live with the full new engine and **caches daily** to `artik_broker/cache/index_<name>_<date>.json` (first call ~35s, then instant; `?refresh=true` to rebuild). Curated constituent lists are `INDEX_TICKERS` in app.py.
- **Portfolio re-run (2026-06-13):** `combined_portfolio_2026-06-13.csv` rebuilt with the NEW engine (archetype + peer-normalized); added an `Archetype` column. Re-run via `artik_broker/rerun_portfolio.py`. Peer-normalization shifted scores (e.g. GOOGL 82→69 within the tech cohort, NVDA 83→89).

## How it's wired
- `app.py` (FastAPI):
  - `GET /` serves `static/index.html`;
  - `GET /api/analyze?symbols=...` returns one row per ticker with the full breakdown embedded (Explain expands client-side — no 2nd call);
  - `POST /api/analyze_portfolio` (multipart `files=`) parses e*Trade/Schwab CSVs, consolidates by symbol, scores each, returns rows + totals. Needs `python-multipart` (already in artikAPIs venv).
- Scoring = the shared **`artik-engine`** package at `artikagents/agents/stock_broker_agent/artik_engine/`
  (`scoring.py` + `peer_universe.py` + `peer_metrics.py` + `data/`), imported cleanly via
  `from artik_engine import scoring` (`score_ticker_live`). No more `sys.path` hacks — it's
  `pip install -e`'d into the artikAPIs venv (run.sh auto-installs on launch). One engine, two
  consumers: artik_broker (website) + the stock_broker CLI agent. Same engine as the portfolio
  table + RUN_STOCK_ANALYSIS.
- `static/index.html` = vanilla JS single page (no build step).
- ETFs (ARKK/EWY/QQQ/…) and invalid tickers return graceful error rows. Max 40 symbols/request.

## Related
- Scoring formula/thresholds: see [[2026-06-13_portfolio-snapshot]] and scoring.py.
- Skill methodology behind it: [[2026-06-13_modular-skills-architecture]] (RUN_STOCK_ANALYSIS.md entry point).
