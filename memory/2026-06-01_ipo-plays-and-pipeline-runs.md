# IPO Plays Feature + Pipeline Run Notes

**Created:** 2026-06-01
**Scope:** The "IPO" insight files (private-company proxy trade tables), how they drive the
dashboard dropdown, and what running the stock-analysis pipeline against IPO proxies revealed.

---

## IPO Plays — what they are

The dashboard sidebar has an **IPO** category (collapsible group) listing four *private*
companies: **Anthropic, OpenAI, SpaceX, Stripe**. None are publicly traded — there is no
ticker / yfinance data for them. Each is backed by a markdown "plays" file that lists
**listed proxy tickers** you can actually trade as IPO-anticipation plays.

### Source files (one per company)
`artikAgents/agents/knowledge_bases/stock_analysis/insight/ipo-<company>.md`
- `ipo-anthropic.md`, `ipo-openai.md`, `ipo-spacex.md`, `ipo-stripe.md`
- Each has a "Trade Signals" table: Action | Symbol | What it is | Today | Trigger Price |
  Why | Stop | Target | Hold. Plus a "Ranked Short-Term Picks" list and risk notes.
- These live under `insight/`, so they ARE loaded into KB context (not excluded) — the
  pipeline sees them when analyzing a proxy ticker and will cite the trigger/stop levels.

### Dashboard wiring
- `build_dashboard.py` builds the sidebar from library files named `<category>-<name>.md`
  → `ipo-spacex.md` becomes **IPO > SpaceX** (special-cased display names for spacex/openai/
  anthropic at build_dashboard.py ~line 75). Category order: Summary → Insights → IPO → Library.

### Proxy mappings (BUY-rated, as of 2026-05-31 files)
| IPO co | Primary listed BUY proxies | Pre-IPO funds |
|---|---|---|
| Anthropic | AMZN ($8B investor), GOOGL (stake+GCP), NVDA (chips) | ARKVX, DXYZ |
| OpenAI | MSFT (~49% econ), NVDA, CRWV | ARKVX, DXYZ |
| SpaceX | TMUS (Starlink d2c), RKLB, ASTS, MOG.A | ARKVX, DXYZ |
| Stripe | PYPL, ADYEY, SHOP, TOST, FOUR | ARKVX, DXYZ |
- AVOID-tagged in files: ORCL/AAPL (OpenAI, blown off), GOOGL-as-SpaceX, MSFT-as-Anthropic,
  generic AI ETFs (BOTZ/AIQ/ROBO — exposure too diluted).

---

## CRITICAL nuance: pipeline scores INVESTMENT merit, IPO files score TRADES

The pipeline (`run_analysis.py` → `agent.py`, 100-pt model) rates **medium-to-long-term
investment quality**. The IPO `.md` tables are **short-term trade triggers**. These DISAGREE
on purpose. When a proxy is "BUY" in the table but AVOID in the pipeline, it's a trade-only
setup, not an investment. Always present both lenses; don't let the pipeline AVOID override a
valid swing-trade trigger (and vice-versa).

### Runs done 2026-06-01 (skill = `lib-stock_analysis_skill`, model claude-opus-4-8)
- **GOOGL** → BUY 83.4/100. The one clean investment-grade buy; sitting on lower BB, entry
  $376–378 (matches insight $378 trigger), stop $345–348, targets $410→430→470. RS rank 100.
- **MSFT** → HOLD/WATCHLIST 73.2. Great business but spiked to $460 (RSI 73, %B 1.26, RS 0).
  Don't chase; wait $419 (20DMA) / $403 (50DMA), stop $392.
- **TMUS** → AVOID 16/100. Stage-4 downtrend, below all MAs, EPS contracting, leverage >2.0.
  Only the separate $185–188 Starlink-proxy swing trade (stop $180) — NOT an investment.
- **PYPL** → AVOID 44/100. Value trap (cheap PEG 0.81 but stalling growth, RS 0). Only a
  speculative Stripe-IPO re-rating swing ($43–45, stop $41, target $52–60).
- **CBRS** (Cerebras, earlier) → SELL/AVOID 29.7. Stage-4 collapse, RS rank 0, neg FCF, P/E ~496.

---

## Pre-IPO fund vehicles: DXYZ vs ARKVX

- **DXYZ** (Destiny Tech100) = NYSE **closed-end fund**, `quoteType=EQUITY` on yfinance →
  pipeline runs fine but scores ~0 on fundamentals (no operating business). Got **18.8/100
  AVOID**. Trades at a **large, volatile premium to NAV** — premium-collapse is the core risk.
  Just round-tripped a parabola $19.71→$72.87→$49. Wait for $30–32 (200DMA) base w/ premium
  compressed before touching. Sub-2% speculative tracker at most.
- **ARKVX** (ARK Venture Fund) = interval **MUTUALFUND** on yfinance (no shortName, no
  fundamentals/RSI/MACD) → **pipeline can't meaningfully analyze it**. Priced AT NAV (~$52),
  **no premium-to-NAV risk** — the playbook's preferred clean pre-IPO vehicle. Downsides:
  illiquid (periodic/quarterly redemptions, can gate), accredited/min requirements, higher ER.
  Months-long hold to IPO, not a swing trade.
- Rule of thumb captured in files + confirmed: **for clean pre-IPO equity exposure,
  ARKVX-at-NAV > DXYZ-at-premium.**

### yfinance quoteType gotcha
Closed-end funds (DXYZ) report `EQUITY` and flow through the pipeline; interval/mutual funds
(ARKVX) report `MUTUALFUND` with null fundamentals and break the 100-pt scoring. Check
`quoteType` before assuming a "fund" ticker can be analyzed.
