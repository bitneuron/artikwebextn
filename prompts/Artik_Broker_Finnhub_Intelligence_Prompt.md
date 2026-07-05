# Artik Broker — Finnhub Intelligence Provider Prompt

_Submitted 2026-07-04. Implemented in commit `9c1a1dd` (Intelligence layer) + `de94499`
(Copilot context). ADDITIVE — the existing Artik Engine/scoring/recommendation logic is
unchanged. See [memory: etrade-integration] work log._

---

Integrate Finnhub into ArtikBroker as an Intelligence Provider only, not as an additional market data or fundamentals provider. The existing provider architecture should remain unchanged: Portfolio → E*TRADE, Market Data → Yahoo Finance, Technical Indicators → Alpha Vantage + existing Artik technical calculations, Fundamentals → Financial Modeling Prep, AI Analysis → Claude/OpenAI, and add Intelligence → Finnhub.

Do not modify, replace, or refactor any existing Artik Engine logic, Artik scoring algorithms, signal generation, technical indicator calculations, fundamental analysis, AI prompts, weighting formulas, decision rules, or recommendation engine. Preserve every existing Artik Engine capability exactly as it exists today. The only change should be the introduction of a new Intelligence component that enriches the existing analysis.

Do not use Finnhub for quotes, historical prices, financial statements, ratios, valuation, or technical indicators since those are already covered by Yahoo Finance, Alpha Vantage, and Financial Modeling Prep. Instead, enhance the existing Stock News Collector Agent to collect and persist Company News, News Sentiment, Analyst Recommendation Trends, Insider Transactions, Insider Sentiment, Institutional Ownership, SEC Filings, Earnings Events, IPO Calendar, ESG (if available), and other intelligence data from Finnhub.

Expand the existing Signals tab from only displaying News Intelligence into a comprehensive Intelligence Dashboard while preserving the existing UI, styling, layout, and user experience. Add reusable cards for News Intelligence, Analyst Signals, Insider Activity, Institutional Ownership, SEC Filing Intelligence, Earnings Signals, and a new Composite Intelligence Signal.

- News Intelligence: Positive/Negative/Neutral counts, overall sentiment, confidence, top headlines, breaking news, last updated.
- Analyst Signals: Strong Buy/Buy/Hold/Sell/Strong Sell recommendation trends with month-over-month changes → Bullish/Neutral/Bearish signal with confidence.
- Insider Activity: CEO purchases, director purchases, executive sales, total insider buying/selling, net insider activity → AI-derived bullish/bearish signal with reasoning.
- Institutional Ownership: major ownership changes, fund accumulation/distribution → Accumulation/Distribution/Neutral.
- SEC Filing Intelligence: latest 10-K/10-Q/8-K/proxy summarized via Claude/OpenAI (revenue/margin/guidance/buybacks/risks/management commentary) → intelligence signal.
- Earnings Signals: next earnings date, historical EPS surprises, revenue surprises, estimate revisions → AI earnings outlook.
- Composite Intelligence Signal: aggregates News + Analyst + Insider + Institutional + SEC + Earnings into a single Bullish/Neutral/Bearish score with confidence and timestamp.

The only change to the Artik Score calculation should be adding a new Intelligence component. Keep all existing scoring logic, formulas, thresholds, AI reasoning, and calculations exactly as they are today, and simply introduce Intelligence as an additional weighted factor without changing how existing Technical, Fundamental, and Risk scores are computed. Rebalance the overall weighting so the final score becomes Technical (30%), Fundamental (35%), Intelligence (20%), and Risk (15%), while preserving the existing internal calculations for each category.

Enhance Deep Analysis by supplying the new intelligence signals to Claude/OpenAI as additional context only; do not change the existing Deep Analysis prompt structure or reasoning flow except to append the new Intelligence section. Include News Intelligence, Analyst Recommendation Trends, Insider Activity, Institutional Ownership, SEC Filing Summary, Earnings Signals, Composite Intelligence Signal, raw Finnhub data, timestamps, confidence scores, and AI-generated summaries.

Every intelligence signal should be clickable and display a detailed view showing the source (Finnhub), provider timestamp, confidence score, raw metrics, historical trend, AI explanation, why the signal matters, and its impact on the Intelligence score and overall Artik Score. Maintain historical snapshots of all intelligence signals and allow users to view Today, 7-Day, 30-Day, and 90-Day trends with charts. Generate a concise AI executive summary such as "Insider buying remains strong while analyst upgrades increased this month. Recent earnings exceeded expectations and institutional ownership continues to rise. Overall Intelligence remains Bullish with High confidence."

Update the Provider Status panel to include Yahoo Finance, Alpha Vantage, Financial Modeling Prep, Finnhub Intelligence, and Claude/OpenAI, displaying success or failure for each provider. Continue to use Yahoo Finance as the primary quote provider, Alpha Vantage for technical indicators, Financial Modeling Prep for fundamentals and financial statements, and Finnhub exclusively for intelligence and event-driven data. Cache Finnhub responses to reduce API usage, gracefully continue stock analysis if Finnhub is unavailable, and simply mark the Intelligence section as temporarily unavailable without impacting any existing Artik functionality.

This implementation must be fully backward compatible. Existing stock analysis results should remain unchanged except for the addition of the new Intelligence component. Do not remove, rename, modify, or regress any existing Artik Engine features, scores, APIs, prompts, UI components, calculations, or business logic. The objective is to extend the Artik Engine—not redesign or refactor it—by adding a new Intelligence dimension while preserving all existing behavior.

---

### Follow-up (same feature): Copilot context
> when i click on ask copilot about a stock. all everything to be seen from portfolio and also include everything seen from detail section including analyst signal and composite signal

Implemented in commit `de94499`: `askCopilotStock` now attaches the engine detail + intelligence
(analyst + composite + insider/institutional/SEC/earnings + AI summary) + deep multi-provider data
(FMP statements/ratios/valuation + intelligence-adjusted score) + the user's portfolio holding.
Backend: `/api/stocks/analyze/{ticker}?skip_ai=true` builds the context fast (no deep-analysis LLM).
