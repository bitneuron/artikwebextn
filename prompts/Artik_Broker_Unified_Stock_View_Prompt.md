# Artik Broker — Unify Explain & Details into a Single Stock Analysis View

_Submitted 2026-07-04. Implemented in commit `f88c3da` (+ `4b1babf` for the Copilot button).
UI/UX consolidation only — no engine/scoring/API/logic change. See [memory: etrade-integration]._

---

Refactor ArtikBroker to use one canonical Stock Analysis page across the entire application.
Eliminate duplicate "Explain" and "Details" views and replace them with a single shared
experience while preserving all existing Artik Engine logic, calculations, scoring, AI prompts,
APIs, and business rules. This is strictly a UI/UX consolidation and must not change any
investment recommendations or scoring behavior.

- **One canonical Stock Analysis View** used everywhere: Portfolio, S&P 500, Dow 30, Watchlist,
  Favorites, Search Results, AI Recommendations, ETF Screener, future stock lists. Only one
  implementation of the stock detail view.
- **Retire the old inline expandable Explain renderer** completely. Explain becomes the entry
  point into the canonical page; there is no longer a separate "Details" button.
- **Single source of truth**: all pages consume the same normalized Stock Analysis model
  (stock info, Artik Engine output, AI summary, technical, fundamental, financial statements,
  trade plan, news, intelligence, provider status, confidence, historical signals). No
  duplicate data loading or calculations.
- **Portfolio context**: when opened from Portfolio, pin a "YOUR POSITION" card under the header
  (shares, average cost, current price, market value, unrealized gain, portfolio weight, holding
  since). When opened from S&P/Dow/Search/Watchlist, show "No Position / Add to Watchlist /
  Analyze / Create Trade Plan". Rest of the page identical.
- **Tabs unchanged**: Overview, Technicals, Fundamentals, Deep Analysis, Signals, News, Peers,
  Trade Plan. Move everything Explain showed into the appropriate tab (formula/breakdown/
  strengths/risks/technicals/FMP ratios/AI analysis/provider status/confidence/intelligence-
  adjusted score). Signals keeps the Intelligence Dashboard (Finnhub intelligence only).
- **Navigation**: every place that opened Explain or Details now opens Stock Analysis via the
  same route/component. Never two different stock pages.
- **Preserve existing logic**: do NOT modify Artik Engine, score calculations, technical/
  fundamental/risk/intelligence scoring, archetype logic, multipliers, penalties, AI prompts,
  AI reasoning, recommendation engine, Buy/Sell/Hold logic, APIs, or provider integrations.
- **Shared components** (StockHeader, PortfolioPositionCard, AISummaryCard, ScoreBreakdownCard,
  FormulaCard, StrengthsCard, RisksCard, TechnicalCard, FundamentalCard, FinancialStatementsCard,
  ProviderStatusCard, IntelligenceDashboard, TradePlanCard, NewsCard); avoid duplicated HTML/
  components.
- **Performance**: load data once; all tabs reuse the same normalized stock object; no duplicate
  API calls when switching tabs; lazy-load expensive sections (News, Deep Analysis, Intelligence
  History) only when first opened.
- **Routing**: `/stocks/:ticker` with optional `?source=portfolio|watchlist|sp500` used only to
  decide whether to show the Portfolio Position card.

### Acceptance
Only one Stock Analysis page; old inline Explain removed; Explain always opens it; Details button
removed; all pages use it; portfolio context only for holdings; all Artik Engine logic unchanged;
all provider integrations still work; no duplicate UI components; no duplicate API calls; existing
functionality preserved.

---

### Follow-up (commit `4b1babf`) — Analyze with Artik Copilot button
> When the user clicks Explain → from any stock row, open the unified Stock Analysis page. Inside
> that page, add a prominent 🤖 Analyze with Artik Copilot button near the stock header and AI
> Executive Summary. Do not open Copilot directly from the table row. Flow: Portfolio/S&P/DOW row →
> Explain → Unified Stock Analysis page → Analyze with Artik Copilot. When clicked, open the existing
> Copilot and preload the full normalized stock analysis context already loaded on the page (Artik
> Score, recommendation, AI summary, technicals, fundamentals, FMP, Alpha Vantage, Finnhub
> intelligence, signals, trade plan, provider status, confidence, timestamps, portfolio position).
> Do not refetch unless stale. The Copilot answers using the current context so the user can ask
> "Why is this HOLD?", "What are the biggest risks?", "What would make this a BUY?", "Explain the
> intelligence score" without retyping the ticker.
