# Artik Broker — Session Prompts Log (2026-07-04)

All prompts submitted in this working session, in order. The two large feature specs have
their own files: [FMP](Artik_Broker_FMP_Provider_Prompt.md) ·
[Finnhub Intelligence](Artik_Broker_Finnhub_Intelligence_Prompt.md).

---

### 1. yfinance rate-limit fallback → commit `bdf5b28` (deployed)
> when i get this error, switch to alpha vantage or use gpt5.5 or claude to get details. could not analyze (YFRateLimitError)

Result: on `YFRateLimitError`, score from Alpha Vantage OVERVIEW fundamentals, else an LLM
estimate, else price-only. Detail panel labels the fallback source.

### 2. Favorites import (screenshot of 15 thematic groups) → localStorage snippet
> add this into favorite for us to analyze later _(image: Photonics/Semis/AI Compute/Networking/
> Memory/AI Systems/Infrastructure/Power/AI Software/AI Cloud/Robotics/Space/Drones/Quantum/Nuclear
> — 43 tickers)_

Favorites are browser-local; delivered a one-paste console snippet that creates the 15 groups
+ assignments in `artik_broker_favorites` / `artik_broker_favorite_groups`.

### 3. Latest models + version fallback → commit `0897fc1` (deployed)
> are you using the latest model of claude and gpt
>
> ok, do all 3. if latest version of model fails, fall back to previous version

Result: `models.py` — reads shared `models.json` + env overrides; ordered chains newest→previous
with `with_fallback()`; GPT bumped gpt-5-mini→gpt-5; FAST tier for the bulk fallback.

### 4. Financial Modeling Prep provider → commit `e7a23e7` (deployed)
Full spec: [Artik_Broker_FMP_Provider_Prompt.md](Artik_Broker_FMP_Provider_Prompt.md). Flow
Yahoo → Alpha Vantage → FMP → Claude/OpenAI; `GET /api/stocks/analyze/{ticker}`; 🔬 Deep Analysis
tab; FMP_API_KEY env only.

### 5. Deep Analysis in Portfolio "Explain" → commit `3ce9ac0` (deployed)
> can you add this details section when you click explain for the stock in your portfolio

Result: `explainPf` renders the engine breakdown then the multi-provider Deep Analysis section below it.

### 6. Finnhub as Intelligence Provider → commit `9c1a1dd` (deployed)
Full spec: [Artik_Broker_Finnhub_Intelligence_Prompt.md](Artik_Broker_Finnhub_Intelligence_Prompt.md).
Intelligence-only (news/analyst/insider/institutional/SEC/earnings); Signals tab → Intelligence
Dashboard; additive `artik_score_with_intelligence` (T30/F35/I20/R15); FINNHUB_API_KEY env only.

### 7. Finnhub API key provided → deployed live (image `v20260704185316`)
> _(screenshot) this is finnhub key: `d94peuhr01qq8ms5majg…` (set as FINNHUB_API_KEY env var; never committed)_

### 8. "Did you change buy/sell/hold logic?" → clarification (no code change)
> where can i see this intelligence board that finnhub is using. did you change any logic for
> recommendation buy, sell and hold

Answer: No — `_status(score)` (BUY≥75 / HOLD≥50 / SELL<50) and the engine are untouched; intelligence
is additive. Dashboard lives on the stock detail → Signals tab.

### 9. Copilot full context → commit `de94499` (deployed)
> when i click on ask copilot about a stock. all everything to be seen from portfolio and also
> include everything seen from detail section including analyst signal and composite signal

Result: `askCopilotStock` attaches engine detail + intelligence (analyst + composite + insider/
institutional/SEC/earnings + AI summary) + deep multi-provider data + the portfolio holding;
`?skip_ai=true` builds the context fast.

### 10. Update memory + save prompts
> update the memory and also include all the prompts submitted

### 11. Unify Explain & Details → commit `f88c3da` (deployed)
Full spec: [Artik_Broker_Unified_Stock_View_Prompt.md](Artik_Broker_Unified_Stock_View_Prompt.md).
One canonical Stock Analysis view everywhere; old inline Explain renderer removed; Explain is the
single entry; Portfolio "YOUR POSITION" card.

### 12. Analyze with Artik Copilot button → commit `4b1babf` (deployed)
Prominent 🤖 button on the unified page header + Overview; preloads the page's loaded context
(engine + intelligence + deep + portfolio), reuses tab caches (no refetch). Table rows never open
Copilot directly. (Included in the Unified Stock View prompt file.)

### 13. S&P 500 / Dow refresh fix → commit `2e7ac89` (deployed)
> refresh button in DOW or SP500 doesn't work _(image: "Scoring Dow 30…")_

Root cause: sequential scoring (~50s, looked frozen). Parallelized (ThreadPoolExecutor 6 workers) →
~12-16s; live elapsed counter + timeout + Retry button.

### 14. News Collector durability → commit `eecb380` (deployed)
> MAKE SURE NEWS COLLECTOR agent is not disabled or deleted, after deployed _(image: collector Running)_

Agent config was ephemeral (`/app/config/agent_schedules.json`) → redeploys reset it to default
(disabled). Fix: persist config in the Litestream-backed users DB (`app_kv`). PROVEN durable across
2 real redeploys.

### 15. Context-aware page search & Copilot → commit `54e6510` (deployed)
Full spec: [Artik_Broker_Context_Aware_Page_Search_Prompt.md](Artik_Broker_Context_Aware_Page_Search_Prompt.md).
ArtikPageSearch bar + Analyze-with-Copilot on Portfolio/S&P500/Dow/Favorites; buildPageAnalysisContext();
`POST /api/copilot/analyze-page`.

### 16. This request
> now upload the memory and also add the prompts to prompts folder
