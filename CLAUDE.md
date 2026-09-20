# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Claude and Codex coexistence

- Claude Code instructions belong in `CLAUDE.md`; Claude project settings, agents, and
  session memory belong in `.claude/`.
- `AGENTS.md` and `.codex/` belong to OpenAI Codex. Do not modify them unless the user
  explicitly requests Codex configuration changes. Do not import them as Claude instructions.
- Keep the tools' settings, permissions, hooks, credentials, and session memory separate.
  Do not symlink or synchronize their configuration directories.
- `memory/` contains shared project documentation; application model settings and `.env`
  files configure the application, not the coding assistant. Preserve actual provider/model
  names regardless of which assistant edits the code.
- When both assistants are active, inspect existing changes before editing, preserve the
  other session's work, and use separate worktrees for tasks that touch the same files.

### Shared file-claim registry (prevents overwriting the other assistant)

Both assistants share one machine-local registry, `.agent-claims.json` (gitignored), managed by
`scripts/agent-claims.py`. A claim records which agent is editing which repo-relative paths; a
claim on a directory covers everything beneath it, and claims older than 8 hours are ignored.

Claude enforces this automatically: a `PreToolUse` hook in `.claude/settings.json` runs the
registry check before every Edit/Write and denies the edit when Codex holds the path. A
`SessionStart` hook reports active claims. Claim with `--agent claude`.

```bash
python3 scripts/agent-claims.py list                                  # who holds what
python3 scripts/agent-claims.py claim   --agent AGENT --task "<short task>" PATH [PATH ...]
python3 scripts/agent-claims.py check   --agent AGENT PATH            # exit 2 = blocked
python3 scripts/agent-claims.py release --agent AGENT [PATH ...]      # no PATH = release all
```

Rules for both assistants:

- Claim the files before the first edit of a task, and release them when the task is done.
- If a claim is refused, do not edit that file. Tell the user which agent holds it and what
  they are doing. Only release another agent's claim when the user says that session is finished.
- A stale claim from a crashed session expires by itself after 8 hours.
- The registry only guards concurrent edits. It is not a lock, and it never replaces reading
  the current file contents before editing them.

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

- **Model policy is per task, not one winner.** `tasks` in `models.json` maps a workload to the
  provider that leads it; the other stays the fallback, so this changes order, never availability.
  Accuracy-first assignments: `extraction` (financial screenshots), `structured` (search planning,
  alerts, copilot commands), `reports` (deep analysis) and `summaries` (news, intelligence) lead with
  Claude; `questions` (data gathering, charts, free-form financial questions) leads with Astra.
  `ARTIK_PRIMARY_MODEL` overrides `primary` but deliberately NOT `tasks` — it is the blunt
  "send everything one way" switch, and it must not silently undo an accuracy assignment.
  Code: `models.task_provider()`, `models.cascade(..., task=...)`; read it at `GET /api/config/models`.
- **No model is ever asked for market data.** When Yahoo and Alpha Vantage both fail, the row says
  "data unavailable". The old path asked an LLM for a 0-100 score from memory, and that score landed
  in the same field as engine-computed ones and was ranked against them with nothing in the UI to
  tell them apart. Do not reintroduce it; a test asserts it is gone.
- **Financial screenshot extraction is cross-checked.** The other provider independently re-reads the
  same image and amounts, dates, signs, line count and account are compared. Disagreements are shown
  and the Apply button changes to require explicit confirmation. Agreement is reported as agreement,
  not as proof.
- **Primary provider: `primary` in `models.json`** (`"openai"` = gpt-6-astra, `"anthropic"` = claude).
  Every AI feature in artikBroker can run on either; `primary` picks which is tried first and the
  other stays as the fallback. Change it with `POST /api/config/models {"primary":"astra"|"claude"}`
  (admin only, writes the file) or the `ARTIK_PRIMARY_MODEL` env var, which wins and makes the API
  refuse to write. Current default: **astra**. On AWS the container filesystem is ephemeral, so set
  the env var there — a file write is lost on the next deploy. Code: `models.PRIMARY`,
  `models.providers()`, `models.cascade()`; read it back at `GET /api/config/models`.
- **Models: one source of truth → `artikAgents/agents/shared/models.json`.** Update versions there.
  Python reads it via `shared/model_config.py`; artikAPIs via `app/model_config.py`; React via
  `src/config/models.js`. The lens-extension keeps its own constants (can't import). Env vars
  (`ANTHROPIC_MODEL`, `OPENAI_MODEL`, `OPENAI_VISION_MODEL`, `OPENAI_CHAT_MODEL`) override.
  Current defaults: anthropic `claude-opus-5`, openai data/chat `gpt-6-astra`, vision `gpt-6-astra`.
- **GPT-5 gotcha:** chat.completions needs `max_completion_tokens` (NOT `max_tokens`), rejects
  non-default `temperature` (drop it), and use `reasoning_effort:"minimal"` so reasoning tokens
  don't eat the answer budget.
- **`.env`** (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `ALPHA_VANTAGE_API_KEY`) lives at
  `artikAgents/agents/.env` (gitignored).
- Stock data: Yahoo Finance (yfinance, no key), with Alpha Vantage fallback/enrichment.
