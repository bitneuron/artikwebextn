# ArtikFinance Transformation Prompt (submitted 2026-07-12)

> The master spec that transformed ArtikBroker into **ArtikFinance** — an AI-powered personal
> finance and investment platform. Iteration 1 shipped (rename, sectioned nav with the
> Financial Statements tree, workbook import engine, /api/finance/* APIs, per-page UI with
> charts/tables/insights + Copilot integration; deployed + validated). Deferred: exports
> (Excel/CSV/PDF), custom date ranges, global finance search, encryption-at-rest, forecasting,
> standalone CLI agent, future modules (budget/retirement/tax planners).
> Workbook path (user-confirmed): artikAgents/agents/knowledge_bases/personal_financial_statement/
> "Financial Statement.xlsx". See memory `artikfinance`.

## Objective
Transform the existing ArtikBroker application into ArtikFinance, an AI-powered personal finance
and investment platform. This is not a rewrite — an expansion. Broker functionality remains
completely intact as one module. ArtikFinance = the single place for brokerage, investments,
personal financial statements, net worth, cash flow, taxes, expenses, AI analysis, autonomous
financial agents.

## Key requirements (abridged from the full spec)
- **Preserve everything**: Portfolio, Analyze, Research, E*TRADE, Schwab, IBKR, Favorites,
  S&P 500, Dow, Trading Desk, Agents, Copilot, History, Skills, Users, Settings, APIs, DB.
- **Rename** every user-facing ArtikBroker→ArtikFinance (logo/title/login/header/nav/AI refs);
  do NOT rename DB tables or API endpoints.
- **New left navigation**: HOME (Dashboard/AI Copilot/Analyze/Research) · BROKER (Portfolio,
  E*TRADE, Schwab, IBKR, Favorites, S&P 500, Dow, Trading Desk, Agents) · PERSONAL FINANCE
  (📑 Financial Statements expandable tree: Assets, Liabilities, Cash Flow, Tax & Income,
  Credit Card Interest, Monthly Expenses, Net Worth) · ADMINISTRATION (History, Skills, Users,
  Settings, Sign Out).
- **Financial Statement Knowledge Base**: bundled workbook is the canonical import source; on
  startup import all worksheets (assets/liability 2015-2021 + 2022 onward merged into one
  timeline, Cashflow, Tax-Income, Credit Card Interest, Monthly_Expense_New), normalize,
  persist to dedicated financial_* tables; DB is the runtime source; re-import + import history.
- **Pages**: Assets (summary cards, detail table, charts), Liabilities, auto-calculated Net Worth
  (current/history/CAGR/high/low/avg), Cash Flow, Tax & Income, Credit Card Interest, Monthly
  Expenses (auto-categorized), time navigation (month/quarter/year), global search.
- **Dashboard cards** (net worth, assets, liabilities, liquid, brokerage, cash, income, expenses,
  cash flow, debt-to-asset, allocation) drilling into detail pages.
- **AI Copilot**: every Personal Finance page has "Analyze with Artik Copilot" sending page data,
  filters, tables, KPIs, trends; answers e.g. "Why did my net worth decrease?", "Compare 2020 vs
  2025", "Predict my net worth in five years".
- **PersonalFinancialStatementAgent** with KB (workbook, README, prompts, skills, metadata):
  load/import/normalize/derive/expose APIs/provide Copilot context.
- **AI insights** auto-generated (net worth YoY, liquidity, mortgage delta, allocation shares,
  savings rate) on dashboard and pages.
- **Future architecture**: budget planner, retirement, estate, insurance, tax planner, goals,
  loan optimizer, mortgage analysis, college savings, forecasting, AI coach.
- **UI**: existing design language, responsive, dark theme, cards, interactive charts, expandable
  nav, sortable tables, exports (Excel/CSV/PDF), print reports.
- **Performance/Security**: lazy-load, cache, validate uploads, encrypt at rest where appropriate,
  authenticated access only, audit imports.
