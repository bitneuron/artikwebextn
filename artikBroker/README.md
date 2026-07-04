# artikBroker

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
cd artikBroker
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
  `../artikAgents/agents/stock_broker_agent/` (`from artik_engine import scoring`,
  `score_ticker_live`) — live yfinance data, no API key. Installed editable into the
  venv (`run.sh` does this automatically; or `pip install -e
  ../artikAgents/agents/stock_broker_agent`). The same package backs the
  stock_broker CLI agent, so the engine has one home and two consumers.

## Agent completion notifications (→ Artik Notifier → Slack)

Every managed agent posts a notification when it reaches a **terminal state**
(`completed` / `failed` / `cancelled` / `timeout` / `skipped`). Notifications are routed
through the **centralized Artik Notifier API** (`POST /api/v1/notifications/slack`), which
forwards them to Slack **#artik-notify** — so all Artik apps share one notification system
instead of each talking to Slack directly.

**How it works (generic — no per-agent code):** the `notifications/` package
(`client.py` · `events.py` · `schemas.py`) holds an env-driven client; a single lifecycle
hook in `agent_runner._worker()` calls `notify_agent_terminal(...)` after every run, so
**all current and future agents are covered automatically**. The client retries with
backoff, times out, logs every attempt (never the API key), and **never raises** — a
notification failure cannot break agent execution. Status→severity:
completed→success, failed→error, cancelled→warning, timeout→error, skipped→info.

**Configuration** (see `.env.example`; secrets live in env / Secrets Manager, never in git):

| Variable | Purpose |
|----------|---------|
| `NOTIFICATIONS_ENABLED` | `true`/`false` master switch |
| `ARTIK_NOTIFY_API_URL` | Base URL of the Artik Notifier service |
| `ARTIK_NOTIFY_API_KEY` | Must match one of the Notifier's `NOTIFY_API_KEYS` |
| `ARTIK_BROKER_APP_NAME` | `source_app` in the payload (default `artikBroker`) |
| `ARTIK_BROKER_BASE_URL` | Builds the "View Job" link |
| `NOTIFICATION_TIMEOUT_SECONDS` / `NOTIFICATION_RETRY_COUNT` | Transport tuning |

**Enable/disable:** set `NOTIFICATIONS_ENABLED=false` to turn off; unset URL/key also
disables (logged, no error). **Test locally:** `python -m pytest tests/` (no network —
the HTTP transport is injectable). **Add a future agent:** nothing to do — if its run
goes through `agent_runner`, it notifies automatically. **Troubleshoot:** check the
`artikbroker.notifications` logger (CloudWatch in prod) — it records agent, job id,
status, attempt count, and the error on failure.

## E*TRADE brokerage connection (OAuth 1.0a)

The **E*TRADE** menu lets a signed-in user connect their E*TRADE account and view
accounts, balances, and portfolio positions. It's a standard three-legged OAuth 1.0a
flow (`etrade.py`, HMAC-SHA1 signed with the stdlib — no external OAuth dependency):

1. **Connect** → server fetches a request token and returns the E*TRADE authorize URL
   (opens in a new tab).
2. You sign in on E*TRADE, approve access, and copy the **verification code**.
3. **Verify** → server exchanges it for an access token (kept server-side, in memory).
4. Accounts / **Balance** / **Portfolio** load from `/api/etrade/*`.

**Config** (secrets — env / Secrets Manager only, never committed; see `.env.example`):

| Variable | Purpose |
|----------|---------|
| `ETRADE_CONSUMER_KEY` / `ETRADE_CONSUMER_SECRET` | OAuth consumer credentials from developer.etrade.com |
| `ETRADE_ENV` | `sandbox` (apisb.etrade.com) or `live` (api.etrade.com) |

Notes: the consumer secret is never sent to the browser (only a `configured` flag).
Access tokens expire end-of-day ET and are held in memory, so you re-connect after a
redeploy or a new day. Endpoints require a logged-in user; each user connects their own
account. Request your **live** key at https://developer.etrade.com/getting-started.

## Notes / limits

- ETFs/funds (ARKK, EWY, QQQ, …) return an "engine does not apply" row — the
  fundamental model only scores operating companies.
- Invalid/delisted tickers return a graceful error row.
- Max 40 symbols per request. Prices are live (last close when market is shut).
- Recent IPOs (< ~1 yr history) score unreliably — technicals need history.
