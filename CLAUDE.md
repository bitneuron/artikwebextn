# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Read this first

Before doing anything, read `memory/README.md` — it is the source of truth for the stock-analysis
pipeline, the scoring-engine business logic, and the artikBroker web app. The most authoritative
single file is `memory/2026-06-13_scoring-engine-business-logic.md`.

## Repository layout (superproject + 3 git submodules)

```
ArtikProjects/                # superproject
├── artikBroker/              # FastAPI + vanilla-JS stock web app (deployed to AWS App Runner)
├── artikAPIs/    (submodule) # Unified FastAPI backend, port 8000
├── artikAgents/  (submodule) # React frontend (src/) + Python CLI agents (agents/)
└── artikTools/   (submodule) # Next.js/Vite app + lens-extension/ (Chrome extension)
```

Submodules are **gitlinks with no `.gitmodules`** — each has its own remote, and the superproject
records only a commit pointer. Commit inside the submodule first, then commit the updated pointer
in the superproject.

## Commands

There is **no test suite** in this repo (the only `test_*.py` files are inside `artikAPIs/venv`).

| Task | Command |
|------|---------|
| Run artikBroker (local) | `cd artikBroker && ./run.sh` → http://localhost:8100 |
| Run artikAPIs (local) | `cd artikAPIs && venv/bin/python -m uvicorn app.main:app --port 8000` (omit `--reload` to require manual restart after router edits) |
| Run artikAgents frontend | `cd artikAgents && npm run dev` (`npm run build`, `npm run lint`) |
| Run artikTools | `cd artikTools && npm run dev` (`npm run build`, `npm run lint`) |
| Ship artikBroker to AWS | `./artikBroker/redeploy.sh` (run from superproject root — image-only swap, preserves secrets/roles) |

`artikBroker/run.sh` uses `../artikAPIs/venv` and auto-installs the `artik-engine` package
(`pip install -e ../artikAgents/agents/stock_broker_agent`) if missing. There is one shared venv at
`artikAPIs/venv` used by both the API and artikBroker.

Generated artifacts are **never hand-edited**: regenerate the agent dashboard by editing
`build_dashboard.py` and re-running it (do not edit the produced `index.html`).

## Architecture

### Scoring engine (`artik_engine`) — the core
The pip-installable package at `artikAgents/agents/stock_broker_agent/artik_engine/` (`scoring.py`,
`peer_metrics.py`, `peer_universe.py`) is the shared brain. Both artikBroker and the CLI agents
import it; `score_ticker_live(ticker)` pulls live yfinance fundamentals and returns the score plus
the full breakdown (`base_metrics_used`/`skipped`, `archetype`, `multiplier_reason`).

Formula: `final = clamp((base − penalties) × archetype_multiplier, 0, 100)`. Six categories score via
peer-relative percentiles against an S&P 500 sector cohort, with sector-aware threshold fallback.
`classify_archetype()` → COMPOUNDER / HYPERGROWTH / FINANCIAL / ENERGY / CYCLICAL / TURNAROUND, which
selects the multiplier. Sector-specific branches (FINANCIAL/ENERGY/RETAIL/CYCLICAL) change which
metrics count. See the memory business-logic file before changing any scoring rule.

### artikBroker (`artikBroker/app.py` + `static/index.html`)
FastAPI + single-file vanilla JS. Reuses `artik_engine` for scoring. Tabs: Analyze · Portfolio ·
S&P 500 · DOW (sortable, per-row Explain). Features: AI Search (NL query → Claude, fallback to GPT →
engine scores), Alpha Vantage enrichment (`alpha_vantage.py`, key from env, never exposed),
server-side search history (`history_store.py`: S3 on AWS, local folder in dev). Auth gate
(login form + signed cookie + pbkdf2 hash) activates only when `APP_PASSWORD_HASH`/`APP_SECRET` are
set; unset locally = open for dev. Deploys to AWS App Runner with secrets in Secrets Manager.

### artikAPIs (`artikAPIs/app/`)
Unified FastAPI backend for artikTools and artikAgents. `main.py` mounts routers (`app/routers/`,
e.g. `stock_analysis`, `news_intelligence`, `financier`, `plaid`, `auth`, `notes`); business logic
lives in `app/services/`. JSON-file storage. Exposes model config to frontends at
`GET /api/config/models`. Swagger at `/docs`.

### CLI agents (`artikAgents/agents/`)
Python Claude-powered agents (stock_broker, company_research, macro_research, news_intelligence,
research_paper, gmail). Shared pattern: each agent has a `knowledge_base.py` delegating to
`shared/kb_loader.py`; knowledge bases live in `agents/knowledge_bases/<name>_knowledge_base/`;
agents with `save_*` tools persist memory back into their KB across sessions.

## Cross-cutting conventions

- **Models: one source of truth → `artikAgents/agents/shared/models.json`.** Update versions there.
  Python reads it via `shared/model_config.py`; artikAPIs via `app/model_config.py`; React via
  `src/config/models.js`. The lens-extension keeps its own constants (can't import). Env vars
  (`ANTHROPIC_MODEL`, `OPENAI_MODEL`, `OPENAI_VISION_MODEL`, `OPENAI_CHAT_MODEL`) override.
  Current defaults: anthropic `claude-opus-4-8`, openai data/chat `gpt-5-mini`, vision `gpt-5`.
- **GPT-5 gotcha:** chat.completions needs `max_completion_tokens` (NOT `max_tokens`), rejects
  non-default `temperature` (drop it), and use `reasoning_effort:"minimal"` so reasoning tokens
  don't eat the answer budget.
- **`.env`** (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `ALPHA_VANTAGE_API_KEY`) lives at
  `artikAgents/agents/.env` (gitignored).
- Stock data: Yahoo Finance (yfinance, no key), with Alpha Vantage fallback/enrichment.
