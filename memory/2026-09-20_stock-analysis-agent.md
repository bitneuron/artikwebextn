# 2026-09-20 — Stock Analysis Agent (daily engine-decided BUY/HOLD/SELL)

Second managed agent in artikBroker's 🤖 Agents tab (template `stock_analysis_agent`, agent_type
"Equity Analysis"), configured like the Stock News Collector (Run Now / Edit / Clone / Results / Logs /
Enable / delete). Package: `artikAgents/agents/stock_analysis_agent/` (discovery.py, analyzer.py, store.py,
config.py, CLI `stock_analysis_agent.py`, README, tests).

**How a verdict is decided.** `score_ticker_live` → `final` → BUY ≥ 75, HOLD 50–74.9, SELL < 50. These are the
Broker's `_status()` bands, which sit on the engine's `rating_from_score` edges (BUY and AVOID). The bands can be
configured. Web mentions, Yahoo analyst consensus and the LLM brief NEVER change a verdict. Street consensus shows up
as an agrees/disagrees badge. The news overlay moves the verdict only if `verdict_uses_overlay` is on, and the base
score is always kept. An engine failure gives `NO_SCORE` (no estimate).

**Discovery.** Keyless sources: Yahoo `yf.screen` (most_actives, day_gainers/losers, undervalued_large_caps,
growth_technology_stocks), Google News RSS analyst-action/stock-pick queries, CNBC and MarketWatch RSS. Extraction
is deterministic: exchange tag, cashtag, (TICK), "TICK stock", S&P 500 company names. Gotcha found live: brokerages
(MS, BAC, WFC) were showing up as "picks" because they *issued* the calls. Fixed with an actor rule (a firm name
followed by raises/cuts/upgrades/buys…, or preceded by after/as/by, is skipped) plus Google " - Publisher"
stripping. Trust-weighted ranking, `min_mentions` (default 2), `max_candidates` (default 25).

**Broker wiring.** `agents_store` is now template-aware: per-template source catalog (`ANALYSIS_SOURCE_CATALOG`),
`template` in the merged config, `create_instance(template=)`; `tracked_tickers` counts news collectors only.
`agent_runner._analysis_worker` runs one subprocess (timeout `STOCK_ANALYSIS_TIMEOUT`, default 1800 s) and uses a
per-instance data dir `STOCK_ANALYSIS_DATA_DIR/<agent_id>`. `stock_recs.py` keeps a durable copy
(`app_kv` key `stock_recs:<id>`: latest + last 30 runs) so Results survive App Runner redeploys; it also does
results grouping, the Slack digest (`STOCK_RECS_SLACK_WEBHOOK`, opt-in via `slack_digest`) and the brief prompt.
Endpoints: `/api/agents/{id}/results` (branches by template), `/api/agents/{id}/brief` (summaries task,
cached per run_id), `/api/recommendations/latest`. `POST /api/agents` takes `template`. Dockerfile bakes the agent
at `/opt/stock_analysis_agent`.

**Verified 2026-09-20.** 33 agent tests + 13 Broker tests pass (245 total Broker). Live run through the Broker: 10
discovered + 3 watchlist → 3 BUY / 2 HOLD / 7 SELL in ~9 s. Brief accurate. UI checked in Chrome (card Picks tile,
Results sections/expand/evidence, Edit form save round-trip, Add Configuration chooser).
**Deployed 2026-09-20 as `v20260920205127` (built from the working tree; NOT git-committed).** The default instance ships Disabled (daily 06:30 America/Los_Angeles).
Agents routes are not admin-gated (same as the News Collector).
