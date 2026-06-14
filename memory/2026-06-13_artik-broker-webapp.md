# artikBroker web app (built 2026-06-13)

A standalone web app to analyze one/many stock symbols and show BUY/HOLD/SELL with an Explain breakdown.

## Location & run
- Folder: `artikBroker/` (project root, sibling to artikAPIs/artikAgents).
- Run: `cd artikBroker && ./run.sh`  (or `../artikAPIs/venv/bin/python -m uvicorn app:app --reload --port 8100`)
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
- **Tabs:** Analyze · Portfolio (saved snapshots by date, sortable + ticker/status search + per-row Explain; shows Archetype col) · **S&P 500** (top 40 by mkt cap) · **DOW** (30). Index tabs hit `GET /api/index/{sp500|dow}` which scores live with the full new engine and **caches daily** to `artikBroker/cache/index_<name>_<date>.json` (first call ~35s, then instant; `?refresh=true` to rebuild). Curated constituent lists are `INDEX_TICKERS` in app.py.
- **Portfolio re-run (2026-06-13):** `combined_portfolio_2026-06-13.csv` rebuilt with the NEW engine (archetype + peer-normalized); added an `Archetype` column. Re-run via `artikBroker/rerun_portfolio.py`. Peer-normalization shifted scores (e.g. GOOGL 82→69 within the tech cohort, NVDA 83→89).

## How it's wired
- `app.py` (FastAPI):
  - `GET /` serves `static/index.html`;
  - `GET /api/analyze?symbols=...` returns one row per ticker with the full breakdown embedded (Explain expands client-side — no 2nd call);
  - `POST /api/analyze_portfolio` (multipart `files=`) parses e*Trade/Schwab CSVs, consolidates by symbol, scores each, returns rows + totals. Needs `python-multipart` (already in artikAPIs venv).
- Scoring = the shared **`artik-engine`** package at `artikAgents/agents/stock_broker_agent/artik_engine/`
  (`scoring.py` + `peer_universe.py` + `peer_metrics.py` + `data/`), imported cleanly via
  `from artik_engine import scoring` (`score_ticker_live`). No more `sys.path` hacks — it's
  `pip install -e`'d into the artikAPIs venv (run.sh auto-installs on launch). One engine, two
  consumers: artikBroker (website) + the stock_broker CLI agent. Same engine as the portfolio
  table + RUN_STOCK_ANALYSIS.
- `static/index.html` = vanilla JS single page (no build step).
- ETFs (ARKK/EWY/QQQ/…) and invalid tickers return graceful error rows. Max 40 symbols/request.

## Added 2026-06-14
- **AI Search (natural language):** the Analyze box accepts plain English OR tickers (auto-detected:
  comma/space-separated 1–6-letter tokens → `/api/analyze`; otherwise → `/api/search`). `/api/search`
  uses a **provider cascade — Claude (`claude-opus-4-8`) first, auto-fallback to OpenAI (`gpt-5-mini`)**
  on any failure (e.g. Anthropic low credits). The LLM only parses intent + proposes candidate tickers;
  the engine still produces all scores. Results show an intent-summary banner (+ "via GPT/Claude") and a
  per-row "why matched". Scores candidates in parallel (ThreadPoolExecutor) + applies hard filters
  (RSI/score/sector/status/macd) against live values.
- **Sortable columns:** click any header on Analyze / S&P 500 / DOW to sort (▲▼), click to flip; default
  Artik Score ↓, error rows last. Shared `sortRows`/`sortHead` helpers; portfolio tab already had it.
- **Alpha Vantage enrichment** (`alpha_vantage.py` + `/api/enrich/{ticker}`): an on-click button in each
  Explain panel loads **Bollinger Bands** (price vs upper/mid/lower + position label) + an AV
  **fundamentals** cross-check. On-click + **daily-cached per ticker** (free tier = 25 calls/day).
  yfinance stays the engine's source. `analyze_one` also has a **yfinance→AV price fallback**
  (GLOBAL_QUOTE) so failed tickers still show a price. Key from env (`ALPHA_VANTAGE_API_KEY`) — never
  hardcoded/logged. See [[2026-06-13_artikbroker-aws-deploy]] for AWS/secret/deploy details.

## Added 2026-06-14 (deployed)
- **Portfolio Refresh button** (`GET /api/portfolio/refresh?date=`): re-scores a saved snapshot's
  holdings against LIVE data — recomputes price/score/RSI/status/archetype/value/P&L while keeping
  qty + cost_basis from the broker CSV. Scores all holdings via a direct ThreadPool (NOT `_score_many`,
  which caps at 25 for AI Search). ETFs/unscored tickers fall back to `_live_price()` so totals stay
  right (verified: refresh reproduces the snapshot's $1.05M / +30.6%). Not cached — always live.
- **Past Searches tab + server-side history** (`history_store.py`, `/api/history` CRUD): every
  Analyze/AI search is saved (query + full results). Backend chosen by env — **S3 on AWS**
  (`HISTORY_S3_BUCKET`), **local folder** `search_history/` in dev. View = cached results, Re-run = live,
  + delete/clear. Capped 50, metadata-only listing. Replaced the earlier localStorage version (per-browser)
  so history survives redeploys + is cross-device. See [[2026-06-13_artikbroker-aws-deploy]].
- **diagrams.html**: standalone non-technical component + search-sequence diagrams (Mermaid via CDN).

## Related
- Scoring formula/thresholds: see [[2026-06-13_portfolio-snapshot]] and scoring.py.
- Skill methodology behind it: [[2026-06-13_modular-skills-architecture]] (RUN_STOCK_ANALYSIS.md entry point).
