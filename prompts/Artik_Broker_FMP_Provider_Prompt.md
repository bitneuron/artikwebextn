# Artik Broker — Financial Modeling Prep (FMP) Provider Prompt

_Submitted 2026-07-04. Implemented in commit `e7a23e7` (Deep Analysis pipeline) — see
[memory: etrade-integration] work log. Flow: Yahoo → Alpha Vantage → **FMP** → Claude/OpenAI._

---

Integrate Financial Modeling Prep API into ArtikBroker as an additional stock data provider.

Reference:
https://site.financialmodelingprep.com/developer/docs

API base URL:
https://financialmodelingprep.com/stable

API key:
FMP_API_KEY=<provided out-of-band; env only — never commit>

Important security rule:
Do not expose the API key in frontend JavaScript, browser DevTools payloads, logs, or committed files. Store it only in environment variables.

Current ArtikBroker flow:
Yahoo Finance → Alpha Vantage → Claude/OpenAI GPT

New required flow:
Yahoo Finance → Alpha Vantage → Financial Modeling Prep → Claude/OpenAI GPT

Implementation requirements:

1. Create a new backend FMP client/service.
   - Read FMP_API_KEY from environment.
   - Use header authorization where supported: apikey: ${FMP_API_KEY}
   - If an endpoint requires query auth, append: ?apikey=${FMP_API_KEY}
   - Add timeout, retry, and error handling.
   - Never log the API key. Mask API key in all debug/error logs.

2. Add FMP as third data provider in the stock analysis pipeline.
   - Keep Yahoo Finance as first source. Keep Alpha Vantage as second source. Add FMP as third.
   - After collecting and normalizing data from all available providers, send the final merged stock context to Claude or OpenAI GPT.

3. Do not remove existing Yahoo Finance or Alpha Vantage logic. Preserve all existing functionality.
   - Add FMP as an additional fallback/enrichment provider.
   - If Yahoo or Alpha Vantage fails, continue with available data.
   - If FMP fails, continue to Claude/OpenAI with the available Yahoo/Alpha data.

4. Fetch these FMP datasets where available: Company profile, Quote, Income statement, Balance sheet,
   Cash flow statement, Financial ratios, Key metrics, Enterprise value, Analyst estimates, Dividends,
   Stock splits, Earnings calendar/history, SEC filings where available.

5. Suggested FMP endpoints: /profile /quote /income-statement /balance-sheet-statement
   /cash-flow-statement /ratios /key-metrics /enterprise-values /analyst-estimates /dividends /splits
   (all `?symbol=AAPL`).

6. Normalize the data before sending to Claude/OpenAI. Merged object:
   { ticker, providers:{yahooFinance, alphaVantage, financialModelingPrep},
     normalized:{price, technicalIndicators, fundamentals, financialStatements, ratios, growth,
     valuation, dividends, earnings, analystEstimates, dataQuality} }

7. Data priority rules:
   - Yahoo Finance for existing quote/statistics data if already working.
   - Alpha Vantage for technical indicators.
   - FMP for fundamentals, financial statements, ratios, analyst estimates, enterprise value, deeper valuation.
   - If multiple providers return the same field, keep all raw values but choose one normalized value using source priority and freshness.

8. Update the AI prompt sent to Claude/OpenAI. Include raw provider data, normalized merged data, source
   names, timestamp of each provider response, missing fields, data conflicts, data confidence score.
   The AI should explicitly consider: Technical score (AV/Yahoo), Fundamental score (FMP statements+ratios),
   Valuation score (FMP key metrics + enterprise value), Risk score (debt, cash flow, volatility, earnings
   trends), Overall Artik Score.

9. Add backend API endpoint if needed: GET /api/stocks/analyze/:ticker — validate ticker, fetch Yahoo +
   Alpha Vantage + FMP, merge and normalize, send final context to Claude/OpenAI, return AI analysis and
   provider status to frontend.

10. Frontend updates: show provider status (Yahoo/AV/FMP/AI success/failure); FMP fundamentals section;
    financial statement summary (Revenue, Gross profit, Operating income, Net income, EPS, Total assets,
    Total liabilities, Cash, Debt, Operating cash flow, Free cash flow); ratios section (P/E, P/S, P/B,
    ROE, ROA, Gross margin, Operating margin, Net margin, Debt-to-equity, Current ratio, Quick ratio).

11. Add environment config: .env.example FMP_API_KEY=your_financial_modeling_prep_api_key_here. Do not commit the real key.

12. Add tests: FMP client success response; missing FMP_API_KEY; invalid ticker; FMP API timeout;
    FMP rate-limit/error; pipeline continues when FMP fails; pipeline sends merged context to Claude/OpenAI;
    API key is never returned to frontend.

Acceptance criteria:
- ArtikBroker still works with Yahoo + Alpha Vantage. FMP added as the third provider.
- Claude/OpenAI receives combined Yahoo + Alpha Vantage + FMP data.
- API key stored securely, never exposed to browser or logs.
- Frontend shows provider status and enhanced fundamentals from FMP.
- Existing portfolio, E*TRADE, stock scoring, and AI analysis functionality remains unchanged.
