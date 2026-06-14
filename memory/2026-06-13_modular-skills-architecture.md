# Modular Skills Architecture — reorg & entry point (2026-06-13)

Context for the stock-analysis **skill library** under
`artikagents/agents/knowledge_bases/stock_analysis_report/`. This is the reference/skills
layer that sits *behind* the stock-broker pipeline (see
[2026-05-31_stock-analysis-dashboard.md](2026-05-31_stock-analysis-dashboard.md)).

## TL;DR — how to use it
- **To run an analysis:** open `RUN_STOCK_ANALYSIS.md` (the single entry point). Give it tickers.
  - `analyze NVDA AAPL MSFT` → standard pipeline per ticker
  - `--quick` (L2+L5) · `--deep` (adds L6+L7+patterns) · `screen …` (rank) · `--no-mandate` (textbook score)
  - `NVDA use Beneish_M` (or comma-list) → run only that skill
- **To understand the architecture:** open `README.md` (the canonical doc — single source of truth).
- **Index of all skills + mermaid diagrams:** `skills/SKILLS_LIBRARY.md`.

## Canonical folder layout (after 2026-06-13 reorg)
```
stock_analysis_report/
├── README.md               ← architecture (was 2 duplicate arch docs, now merged+deleted)
├── RUN_STOCK_ANALYSIS.md   ← ENTRY POINT (call with tickers)
├── skills/                 ← full engine, one folder per layer L0–L9
│   ├── mandate/            L0  Investment_Mandate · Buy_Criteria · Sell_Criteria · Sector_Policy
│   ├── orchestrator/       L1  Stock_Analysis_Orchestrator (v1.1.0 — loads L0 first)
│   ├── core/               L2  Value·Quality·Growth·Financial_Strength·Technical (100 pts)
│   ├── technical/          L3  CAN_SLIM·Trend_Template·Chart_Pattern·Elliott_Wave
│   ├── business_quality/   L4  Buffett_Moat (0.80–1.20× multiplier)·Management_Quality
│   ├── risk/               L5  Risk_Analysis·Beneish_M
│   ├── quant/              L6  Piotroski·Altman_Z·Factor_Model
│   ├── research/           L7  Earnings_Call·Competitive_Moat_Research·Institutional_Flow
│   ├── portfolio/          L8  Portfolio_Manager·Sell_Discipline
│   ├── agents/             L9  Screener·Research·Portfolio_Manager·CIO
│   └── SKILLS_LIBRARY.md
├── reference/              ← ALL source/methodology docs (read-only)
│   ├── Stock_Analysis_Skill.md (841-line monolith) · Fairlead_Strategy.md
│   └── Fundamental_Analysis.md · Stock_Patterns.md · Technical_Analysis_Summary.md · STOCK_RULES.md
(analyzed reports moved out → knowledge_bases/analyzed_reports/, 2026-06-13)
└── insight/
```

## The key design idea: L0 Mandate
- The generic skills (L1–L9) answer "is this a good stock?"; **L0 mandate** answers
  "is it good *for me*?" — it's *my personal rules* turned into:
  - **hard gates (veto, run first):** price <$5 · sector in avoid-list · D/E >1.5 · negative FCF → `MANDATE_REJECT`; position cap 10% (caps size, never rejects)
  - **soft tilts (adjust final score):** favored sector → +bonus; thesis horizon <6mo → −penalty
- Scoring identity: `final = (base 0–100 + L3 bonuses − L5 penalties) × L4 multiplier`, then L0 gates can veto + tilts adjust.
- Source of my rules: `stock_knowledge_base/rules/investment_rules.md` + `reference/STOCK_RULES.md`.
- `mandate/` lives **inside `skills/`** (not at root) on purpose — it's a skill layer, so the dashboard + API auto-scan it.

## What changed on 2026-06-13 (non-obvious)
1. Merged 2 duplicate arch docs (`Modular_Skills_Architecture.md` + `skills/Stock_Modular_Architecture.md`) → **deleted both**, README is canonical.
2. Built L0 `mandate/` (4 files) from `investment_rules.md` + `STOCK RULES.docx`; moved under `skills/`.
3. Converted `stock_knowledge_base/KR_Library/*.docx` → `reference/*.md`.
4. Moved `Stock_Analysis_Skill.md` + `Fairlead_Strategy.md` into `reference/`.
5. Wired L0 gate/tilt into the Orchestrator (now v1.1.0; added `apply_mandate` input, `MANDATE_REJECT` failure mode).

## Code repointed (because docs were load-bearing for the UI)
The dashboard/API/React read these docs by exact name — moving them required edits:
- `artikAPIs/app/routers/skill_library.py` — `FOLDER_ORDER` gained `mandate` ("L0 · Mandate"); `TOP_LEVEL_DOCS_ORDER` = `SKILLS_LIBRARY.md` (its base is `…/skills/`, can't reach README one level up).
- `artikagents/src/components/SkillLibrary.jsx` — `DEFAULT_DOC = 'SKILLS_LIBRARY.md'` (was `Stock_Modular_Architecture.md`).
- `artikagents/agents/stock_broker_agent/stock_analysis_dashboard/build_dashboard.py` — "Architecture" entry → `README.md`; now also scans `reference/` for Standard/Commercial dropdown docs; `mandate` in `SKILL_FOLDER_ORDER`.
- `artikagents/agents/stock_broker_agent/run_analysis.py` — `architecture`/`readme` alias → `README.md`; resolves `reference/` docs.

## Gotchas / open items
- **Not runtime-verified:** the React dashboard render — `fastapi` isn't installed in the plain shell, so could only verify Python `py_compile` + tree logic. To confirm: run the API + `npm run dev`, check the "L0 · Mandate" group shows.
- Generated PDFs moved out to `knowledge_bases/analyzed_reports/` (2026-06-13) — output separated from methodology source; consumers repointed: `run_analysis.py`, `artikAPIs/.../stock_analysis.py`, `artikAPIs/.../kb_upload.py`.
- The skill_library API base is `…/stock_analysis_report/skills/` (so README at report root is *outside* it — that's why the in-tree overview is SKILLS_LIBRARY.md, not README).
