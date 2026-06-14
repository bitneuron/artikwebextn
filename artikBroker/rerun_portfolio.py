"""Re-score the June-13 portfolio with the NEW engine (archetype + peer normalization)
and overwrite combined_portfolio_2026-06-13.csv (adds an Archetype column)."""
import csv
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
from artik_engine import scoring  # noqa: E402  (installed artik-engine package)

DESTS = [
    Path(__file__).resolve().parent.parent
    / "artikAgents/agents/knowledge_bases/Stock_Portfolio/June-13-2026/combined_portfolio_2026-06-13.csv",
    Path(__file__).resolve().parent.parent / "memory/combined_portfolio_2026-06-13.csv",
]
ETF = {"ARKK", "EWY", "CIBR", "SCHD", "VOO", "QQQ", "SPY", "VTI", "SMH", "IBIT", "DIA", "IWM"}


def _num(s):
    try:
        return float(str(s).replace(",", "").replace("$", "").strip())
    except Exception:
        return None


def status(s):
    return "BUY" if s >= 75 else "HOLD" if s >= 50 else "SELL"


# read qty + cost from the existing combined CSV
src = DESTS[0]
holdings = []
for r in csv.DictReader(src.read_text().splitlines()):
    tag = (r.get("#") or "").strip()
    if tag in ("TOTAL", "AS_OF") or not (r.get("Ticker") or "").strip():
        continue
    holdings.append((r["Ticker"].strip(), _num(r.get("Qty")), _num(r.get("Cost_Basis"))))

rows = []
for i, (tk, qty, cost) in enumerate(holdings, 1):
    arch, price, sc, rat, rsi = "", None, None, "", None
    try:
        if tk not in ETF:
            r = scoring.score_ticker_live(tk)
            s = r["scores"]
            arch = r.get("archetype", "")
            price = r["price"]; sc = s["final"]; rat = s["rating"]
            rr = r["technicals"].get("rsi")
            rsi = round(rr, 1) if isinstance(rr, (int, float)) and rr == rr else None
        if price is None:
            import yfinance as yf
            info = yf.Ticker(tk).info or {}
            price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("regularMarketPreviousClose")
    except Exception as e:
        print(f"  {tk}: ERR {str(e)[:50]}", flush=True)
    mv = (qty * price) if (qty and price) else 0.0
    pl = mv - cost if cost else 0.0
    plp = (pl / cost * 100) if cost else None
    st = status(sc) if sc is not None else ("ETF" if tk in ETF else "?")
    rows.append([tk, arch, qty, cost, price, mv, sc, rat, rsi, st, pl, plp])
    print(f"  [{i}/{len(holdings)}] {tk} {arch} {sc} {st}", flush=True)

rows.sort(key=lambda x: -(x[5] or 0))  # by value desc
tmv = sum(r[5] for r in rows); tc = sum(r[3] or 0 for r in rows); tpl = tmv - tc

for dest in DESTS:
    with open(dest, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["#", "Ticker", "Archetype", "Qty", "Cost_Basis", "Price", "Value",
                    "Score", "Rating", "RSI", "Status", "PL_$", "PL_%"])
        for i, r in enumerate(rows, 1):
            tk, arch, qty, cost, price, mv, sc, rat, rsi, st, pl, plp = r
            w.writerow([i, tk, arch, round(qty or 0, 4), round(cost or 0, 2),
                        round(price, 2) if price else "", round(mv, 2),
                        sc if sc is not None else "", rat, rsi if rsi is not None else "",
                        st, round(pl, 2), round(plp, 1) if plp is not None else ""])
        w.writerow([])
        w.writerow(["TOTAL", "", "", round(sum(r[2] or 0 for r in rows), 2), round(tc, 2), "",
                    round(tmv, 2), "", "", "", "", round(tpl, 2), round(tpl / tc * 100, 1) if tc else ""])
        w.writerow(["AS_OF", "2026-06-13 (new logic: archetype + peer-normalized)", "rerun"])
    print("wrote", dest, flush=True)

print(f"\nDONE: {len(rows)} positions · value ${tmv:,.0f} · P/L ${tpl:,.0f} ({tpl/tc*100:+.1f}%)", flush=True)
