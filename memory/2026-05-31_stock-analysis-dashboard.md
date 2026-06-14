# Stock Analysis Dashboard — Work Log & Reference

**Created:** 2026-05-31 22:06:37 PDT
**Scope:** Stock Broker Agent + dashboard + artikAPIs stock-analysis endpoints.

---

## Architecture overview

Two-model pipeline that analyzes a stock and produces a PDF report:

```
Dashboard (static HTML)  ──SSE──►  artikAPIs (FastAPI :8000)  ──subprocess──►  run_analysis.py  ──►  agent.py
```

### Key files
| File | Role |
|---|---|
| `artikAgents/agents/stock_broker_agent/stock_analysis_dashboard/build_dashboard.py` | Generates `index.html` (the dashboard). All form/JS/CSS lives here as Python strings. Re-run to rebuild. |
| `artikAgents/agents/stock_broker_agent/stock_analysis_dashboard/index.html` | Generated output — DO NOT edit by hand; rebuild from `build_dashboard.py`. |
| `artikAgents/agents/stock_broker_agent/run_analysis.py` | Web-triggered runner. Emits JSON progress lines to stdout for SSE. Parses `--skill=` and `--model=`. |
| `artikAgents/agents/stock_broker_agent/agent.py` | Two-model pipeline. `gather_data()` (OpenAI tool loop) + `synthesize_recommendation()` (selectable model). |
| `artikAgents/agents/stock_broker_agent/chart_analyzer.py` | OpenAI vision analysis of chart PNGs. |
| `artikAPIs/app/routers/stock_analysis.py` | API: `/api/stock/analyze/{ticker}`, `/api/stock/report/{filename}`, `/api/stock/reports`. |
| `artikAPIs/app/routers/skill_library.py` | `/api/library/tree`, `/api/library/file/{rel_path}`. |

### Run the API
```bash
cd artikAPIs && venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```
- venv: `artikAPIs/venv/bin/python` (openai 2.14.0, supports GPT-5).
- run_analysis runs under the API's `sys.executable` (the artikAPIs venv).
- uvicorn started WITHOUT `--reload`, so **restart the API after editing any router**.
- `.env` with `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` lives at `artikAgents/agents/.env`.

### Rebuild the dashboard
```bash
cd artikAgents/agents/stock_broker_agent/stock_analysis_dashboard && python build_dashboard.py
```
Hits yfinance (network) for live signals; takes ~1 min.

---

## Models (current state)

- **Data gathering (Step 1, OpenAI tool loop):** `gpt-5-mini`, `reasoning_effort="minimal"`, `max_completion_tokens=4096`. Constant `OPENAI_MODEL` in agent.py (env override `OPENAI_MODEL`).
- **Vision (chart_analyzer):** `gpt-5`, `reasoning_effort="minimal"`, `max_completion_tokens=2000` (bumped from 800 because GPT-5 reasoning tokens share the completion budget).
- **Synthesis (Step 2, final recommendation):** user-selectable. Default = latest Anthropic `claude-opus-4-8` (constant `ANTHROPIC_MODEL`, env override `ANTHROPIC_MODEL`).

### GPT-5 gotchas (learned)
- GPT-5 requires `max_completion_tokens`, NOT `max_tokens` (the old param errors).
- GPT-5 reasoning tokens count against the completion budget → set generous budgets for short outputs.
- `reasoning_effort="minimal"` makes GPT-5 behave closest to old non-reasoning gpt-4o (fast/cheap).

### Synthesis model registry (agent.py)
```python
SYNTH_MODELS = {"gpt-5-mini":"openai", "gpt-5":"openai", "claude-opus-4-8":"anthropic"}
DEFAULT_SYNTH_MODEL = "claude-opus-4-8"
```
`synthesize_recommendation(user_message, gathered_data, model)` branches by provider. OpenAI path uses a system message + images converted from Anthropic blocks via `_anthropic_imgs_to_openai()`. Anthropic path unchanged (native image blocks). Data-gathering step is ALWAYS OpenAI gpt-5-mini regardless of synthesis choice.

---

## Skill dropdown (the grouped skill picker on the Stock Analysis page)

Built in `build_dashboard.py` → `SKILL_DROPDOWN_OPTIONS`; rendered as `<optgroup label="{folder}/">`.

Group order (top to bottom):
1. `commercial/` → **Fairlead Strategy** (source: `stock_analysis/Fairlead_Strategy.md`, matched by filename)
2. `foundation/` → Modular Skills Architecture, Stock Analysis Skill, Architecture (the former `standard/` group, renamed)
3. `orchestrator/`, `core/`, `technical/`, `business_quality/`, `risk/`, `quant/`, `research/`, `portfolio/`, `agents/` — one per folder under `knowledge_bases/stock_analysis/skills/`.

### Skill id resolution (run_analysis.py)
Dropdown values: `skill-<stem>` (per-folder specs), `lib-<stem>` (report-root .md), special `lib-architecture` → `skills/Stock_Modular_Architecture.md`. Resolver searches `skills/**` then report-root `*.md`. The prompt is augmented with the skill's markdown methodology and instructs the model to follow it. `?skill=` is single-select → "run against that skill only".

---

## PDF reports

- **Saved to:** `knowledge_bases/analyzed_reports/ (moved 2026-06-13)` (changed from report root). Filename: `{TICKER}_analysis{_skillslug}_{YYYYMMDD_HHMMSS}.pdf`. Both CLI and web save here (web uses run_analysis.py).
- **Serve inline:** `GET /api/stock/report/{filename}` → FileResponse, `Content-Disposition: inline`, with traversal guard (rejects `/`, `\`, `..`, non-`.pdf`).
- **List:** `GET /api/stock/reports` → `{"reports": [...]}` newest-first.

### Dashboard PDF viewing
- On analysis completion, the result block auto-renders the new PDF in an inline `<iframe>` (`.sa-pdf-frame`), plus View/Open-in-new-tab/Download buttons.
- **📄 PDF Viewer** button (in `.sa-actions` next to Run Analysis / Clear Results) → `togglePdfViewer()` fetches `/api/stock/reports`, shows a dropdown of all saved reports + inline iframe; selecting one loads it. Toggle again to close.

## KB context exclusions (2026-05-31, later)

When a skill is selected the analysis is driven by that skill's methodology (prompt
augmentation), and two folders are **excluded from KB context everywhere**:
- `analyzed_reports/` (now a top-level sibling, gitignored) — our own generated PDFs (kills the feedback loop)
- `KR_Library/` (under `stock_knowledge_base/`) — reference library, not analysis context

Implementation:
- `shared/kb_loader.py` → `load_knowledge_base(kb_dir, exclude_folders=None)` skips any
  top-level folder OR `<folder>/<subfolder>` label whose name is in the set (case-insensitive).
- `stock_broker_agent/knowledge_base.py` → `EXCLUDE_FOLDERS = {"analyzed_report","kr_library"}`,
  passed to every `_load_kb(...)` call. This drives `agent.KB` → system context + image messages.
- `run_analysis.py` STEP-1 scan mirrors the same `KB_EXCLUDE_FOLDERS` so the "Loaded …" /
  "Scanning" progress log doesn't show excluded files.
- Verified: KB loads 198 blocks across 40 folders, none from analyzed_reports/KR_Library;
  ticker charts (`charts/<TICKER>`) still load.
- NOTE: this is exclusion-only — the rest of the KB (charts, recommendations, company/macro
  notes, live market data) is still used. It does NOT reduce context to *only* the selected
  skill doc. If full skill-only isolation is ever wanted, that's a further change.

---

## Dashboard form fields (current)
Tickers (comma-separated) · Analysis Skill (grouped dropdown) · **Model** (Claude Opus 4.8 default / GPT-5 / GPT-5 mini; persisted to `localStorage` `sa-model`) · API Base URL (default `http://localhost:8000`). Run banner + per-ticker badges show skill + model. Endpoint: `GET {api}/api/stock/analyze/{ticker}?skill={id}&model={model}`.

---

## Verification commands used
```bash
# compile
artikAPIs/venv/bin/python -m py_compile <file>.py
# validate models live (loads .env, tiny call)
# gpt-5 / gpt-5-mini: chat.completions with max_completion_tokens + reasoning_effort='minimal'
# claude-opus-4-8: anthropic.messages.create — all returned 'ok'
# report endpoints: /api/stock/reports (200), /report/<file> (200 application/pdf), traversal → 404
```
