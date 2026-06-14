# Stock Scoring Engine — Complete Business Logic (2026-06-13)

The authoritative reference for how `artikagents/agents/stock_broker_agent/scoring.py` scores a
stock. Used by: artik_broker, the stock_broker_agent pipeline, sp500_screen, RUN_STOCK_ANALYSIS.
Pure Python + yfinance (no LLM). Skill docs: `stock_analysis_report/skills/business_quality/Archetype_Multiplier_Skill.md`
+ `skills/quant/Peer_Normalization_Skill.md`.

## Final formula (unchanged across all upgrades)
```
base   = value + quality + growth + financial_strength + technical + risk   # 0–100
final  = clamp( (base − penalties) × archetype_multiplier , 0 , 100 )
rating = ≥90 STRONG BUY · ≥75 BUY · ≥65 WATCHLIST · ≥50 NEUTRAL · else AVOID
```
Category maxes: Value 15 · Quality 22 · Growth 18 · Financial Strength 13 · Technical 22 · Risk 10.
Penalties capped at 25. Multiplier clamped 0.80–1.20.

## Category scoring — DUAL PATH (dispatch in scoring.py)
Each of `value_score / quality_score / growth_score / fin_strength_score` dispatches:
1. **Peer-percentile path** — if `Inputs.percentiles` is populated, score = weighted avg of the
   company's sector percentiles × category max (`_pct_category`). Metric weights:
   - value: pe .30, forward_pe .20, ev_ebitda .20, pfcf .15, peg .15 (all lower-better)
   - quality: roe .25, roic .25, fcf_margin .20, net_margin .15, gross_margin .15
       - FINANCIAL: roe .45, net_margin .30, fcf_margin .25 (NO gross margin, NO roic — bank ROIC unreliable)
       - ENERGY: roic .45, fcf_margin .45, roe .10 (drop margins)
       - retail (low_margin_model): roe .30, roic .35, fcf_margin .20, net_margin .15
   - growth: rev_growth .6, eps_growth .4
   - financial_strength: debt_equity .55 (lower-better), current_ratio .45
2. **Threshold path** (fallback, sector-aware) — `_value_threshold / _quality_threshold / …` when no
   peers. quality_score threshold branch is itself sector-aware (ENERGY reweights FCF-yield/ROIC/debt;
   retail relaxes margins; FINANCIAL gets net-margin/earnings-yield substitutions via Inputs).

## Real metrics (replaced the old proxies)
- **ROIC** = NOPAT / Invested Capital; NOPAT = `operatingMargins × totalRevenue × (1−0.21)`;
  IC = `TotalDebt + Equity − Cash` (Equity = `bookValue × sharesOutstanding`), with a guard:
  fall back to Debt+Equity if (IC − cash) < 10% of revenue (avoids explosion on cash-rich firms);
  ROA fallback when statements thin; clamp [−0.5, 1.0]. (Old proxy `0.7×ROE` was leverage-inflated.)
- **FCF margin** = `freeCashflow / totalRevenue` (old proxy was net margin).
- For FINANCIAL base, ROIC is overridden to ROE (NOPAT/IC meaningless for banks).

## Archetype classification (`classify_archetype`, deterministic, order matters)
```
Financial Services            → FINANCIAL
Energy                        → ENERGY
Industrials / Basic Materials → CYCLICAL
unprofitable (pm≤0 & eps≤0) & rev<20%  → TURNAROUND
rev>20% & sector in {Technology, Communication Services, Healthcare, Consumer Cyclical} → HYPERGROWTH
else                          → COMPOUNDER
```
Sector identity wins first (a cyclical/financial in a strong year is NOT hypergrowth). `low_margin_model`
flag set when sector == Consumer Defensive or industry ~ retail/grocery/discount.

## Archetype multiplier (`archetype_multiplier`, ranges enforced + clamped 0.80–1.20)
Each archetype uses DIFFERENT metrics, incl. multi-year trend metrics from `compute_trend_metrics`:
- **COMPOUNDER** 0.85–1.20: ROE/ROIC/FCF margin + **margin stability** (elite needs stable margins).
- **HYPERGROWTH** 0.85–1.20: revenue growth + Rule-of-40 + gross margin + **FCF CAGR / improving profitability**; doesn't punish low profit.
- **FINANCIAL** 0.85–1.15: ROE + **efficiency ratio** (cost/income) + revenue growth. NO gross margin. (capital adequacy / credit quality unavailable in yfinance.)
- **ENERGY** 0.85–1.15: FCF yield + debt/EBITDA + ROCE/ROIC + **FCF durability** (% of yrs FCF>0). NOT net margin.
- **CYCLICAL** 0.90–1.15: ROIC + balance sheet + **FCF conversion (FCF/NI)** + **margin stability**. D/E>2 penalty suppressed.
- **TURNAROUND** 0.80–1.05: revenue stabilization + cash burn + **debt reduction** + **profitability progress**. No speculative premium.

## Sector-aware BASE adjustments (so the 100-pt base isn't sector-blind)
- FINANCIAL: gross-margin→net-margin, owner-earnings-yield→earnings-yield, ROIC→ROE, current-ratio→neutral 1.6, **D/E>2 penalty suppressed**.
- CYCLICAL: **D/E>2 penalty suppressed** (captive-finance / capital-intensive).
- ENERGY: quality_score reweighted to FCF-yield + ROIC + debt strength, margins down-weighted.
- RETAIL/Consumer Defensive: relax gross/net margin, credit ROIC + FCF conversion.

## Trend metrics (`compute_trend_metrics`, multi-year statements)
margin_stable (net-margin pstdev<5pp), profit_improving, fcf_cagr, fcf_durability (% yrs FCF>0),
fcf_conversion (FCF/NI), debt_reducing, efficiency_ratio (cost/income). All None → graceful fallback.
**Cost: +~0.8s/ticker** (3 statement fetches). NOT used by the saved-snapshot Portfolio tab (reads CSV).

## Peer normalization (NEW — `peer_universe.py`, `peer_metrics.py`)
- **PeerUniverseService**: reads `stock_broker_agent/data/sp500_constituents.csv` (503 rows; built from
  Wikipedia via `build_sp500_csv()`, GICS→yfinance sector map). `get_peers(ticker, sector, industry, level)`
  returns same-sector tickers (industry level when cohort ≥8).
- **PeerMetricsService**: `peer_metrics_from_info` extracts 15 metrics/peer; `get_sector_metrics` caches
  **daily** per sector to `data/peer_metrics_<date>.json` (lazy build ~15s/sector first time, then reused).
  `compute_percentiles(sector, peers, company_metrics)` → {metric: {value, percentile, tier, n_peers, higher_better}}.
- `percentile_rank(value, peers, higher_better)` (≥5-peer cohort) + `percentile_to_tier` (≥80 elite/≥60 strong/≥40 average/≥20 weak/<20 poor).
- Fed into the 4 category scorers (path 1 above). **Never fails** — try/except → {} → thresholds (spec item 10).

## Explanation outputs (on `score_ticker_live` result, shown in artik_broker Explain + markdown)
- `archetype`, `multiplier_reason` (e.g. "elite growth: rev 85%, R40 103, improving profit")
- `base_metrics_used` / `base_metrics_skipped` (per-sector base substitutions)
- `peer_normalized` (bool) + `peer_explanation` (["ROE: 18.4%, sector percentile 87", …])

## Files
- `scoring.py` — engine (classify_archetype, archetype_multiplier, compute_trend_metrics, _*_threshold + dispatchers, fetch_live_inputs, score_ticker_live, format_analysis_markdown).
- `peer_universe.py`, `peer_metrics.py` — peer layer. `data/sp500_constituents.csv`, `data/peer_metrics_<date>.json`.

## Known limitations (data, not logic)
- Bank ROIC unreliable (NOPAT/IC) → FINANCIAL uses ROE; capital adequacy / credit quality / bank efficiency ratio not in yfinance.
- ENERGY FCF data noisy in yfinance. ROIC depends on bvps×shares / totalDebt fields (ROA fallback).
- interest_coverage & fcf_growth omitted from peer metrics (not in `info`). Guardrail "normalize" now satisfied via percentiles.

## How to run / refresh
- Score: `from scoring import score_ticker_live; score_ticker_live("NVDA")`.
- Rebuild SP500 list: `python -c "import peer_universe as pu; pu.build_sp500_csv()"`.
- Peer cache rebuilds daily automatically (lazy per sector). First multi-sector run is slower while caches build.
