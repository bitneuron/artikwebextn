# Artik Broker — Context-Aware Page Search & Copilot (Portfolio · Dow · S&P · Favorites)

_Submitted 2026-07-05. Implemented in commit `54e6510`. UI/capability enhancement only — no
engine/scoring/API/permission/layout change. See [memory: etrade-integration]._

---

## Objective
Embed the Artik Search experience directly into Portfolio, Dow, S&P 100/S&P 500, and Favorites.
Users can ask natural-language questions about the current page and launch Artik Copilot with the
entire page context for deep AI analysis. UI + capability enhancement only; existing functionality,
workflows, APIs, permissions, and layouts unchanged. One reusable component: **ArtikPageSearch**.

## UX
At the top of each page add an Artik Search section consistent with the Analyze page: search input,
search button, voice input (if supported), suggested prompt chips, and an **Analyze with Artik
Copilot** button.

- Placeholder examples: "Ask about this portfolio…"; example questions like "Which holdings should
  I sell?", "Why is NVDA Strong Buy?", "Which companies are overvalued?", "Summarize this page".
- **Quick chips** — Portfolio: Summarize Portfolio, Top Opportunities, Biggest Risks, Sell
  Candidates, Buy Candidates, Diversification Review, Sector Exposure, Winners vs Losers, Compare
  Holdings. Dow/S&P: Today's Winners, Best Long-Term Investments, Undervalued, Overvalued, Highest
  Quality, Growth Leaders, AI Stocks, Dividend Leaders, Compare Companies. Favorites: Review
  Favorites, Which should I buy now?, Rank my Favorites, Hidden Gems, Compare Favorites.

## Search engine priority
Answer using (1) current page context, (2) existing research cache, (3) existing Artik Intelligence,
(4) existing Deep Analysis, (5) existing AI explanations. Only fetch new external data if research is
missing, cache expired, or the user requested the latest.

## Analyze with Artik Copilot
Every supported page includes the button. When clicked: open the existing Copilot, auto-preload the
entire page context (no copy/paste, no extra action).

## Payload — POST /api/copilot/analyze-page
Include General (page_type, user_query, timestamp, current_user, source, selected_snapshot, filters,
sort_order, search_text, selected_rows, expanded_panels, current_tab, page_state); Portfolio Summary
(health score, value, cash, cost basis, gain/loss + %, Strong Buy/Buy/Hold/Sell/Sell-candidate counts,
sector/industry allocation, diversification + risk metrics, benchmark comparison, timestamps); every
visible stock (ticker, company, sector, industry, archetype, quantity, average_cost, current_price,
market_value, market_cap, weight, unrealized gain/loss + %, Artik Score, recommendation, RSI, moving
averages, MACD, Bollinger, valuation/fundamental/dividend metrics, analyst rating, target, volatility,
existing explanation, status, favorite/watchlist status); research results per stock where already
generated (overview, business summary, Deep Analysis, Artik Intelligence, Explain output, AI summary,
fundamental/technical/valuation/competitive analysis, industry outlook, news/SEC/earnings/guidance
summaries, insider transactions, institutional ownership, analyst up/downgrades, price targets,
catalysts, risks, opportunities, sentiment scores, research timestamp/cache version); search/screening
results if displayed; market context (indices, sector performance, VIX, yields, macro, breadth); user
context (filters, sort, selected tickers, expanded rows, visible columns/stocks, UI state).

## Security
NEVER include OAuth/access/refresh tokens, API keys, passwords, cookies, session secrets, internal
credentials, broker account secrets, or PII. Only normalized business data.

## Copilot response
Executive Summary · Key Insights · Risks · Opportunities · Portfolio Recommendations
(Buy/Hold/Sell/Reduce/Increase/Monitor) · Company Analysis (bull/bear/risks/catalysts/technical/
fundamental) · Comparison · Suggested Next Questions.

## Performance
Reusable `buildPageAnalysisContext()` shared across Portfolio/Dow/S&P/Favorites; no duplicate code;
reuse research cache; lazy-load external research only when necessary.

## Acceptance
Ask Artik on Portfolio/Dow/S&P/Favorites; NL questions; Analyze with Copilot opens with full page
context; payload includes all visible stocks + any research/search results; existing intelligence/
deep/research reused before fetching; no credentials ever sent; existing functionality + layouts
unchanged; responsive (desktop/tablet/mobile); existing dark theme/design system.

_Implementation note: the app has S&P 500 (top 40) + Dow; there is no separate "S&P 100" page, so the
component is on those four lists. Fields not tracked by the app (VIX, treasury yields, Reddit/Twitter
sentiment, cash balance, market breadth, etc.) are gracefully omitted; everything available is sent._
