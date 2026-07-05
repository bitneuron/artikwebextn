"""Intelligence signal computation from Finnhub data (pure functions — no network/LLM).

Turns raw Finnhub datasets into Artik intelligence signals: News, Analyst, Insider,
Institutional Ownership, SEC Filings, Earnings, and a Composite Intelligence Signal.
Each signal is Bullish / Neutral / Bearish with a 0-100 score and a confidence. These are
ADDITIVE — they never touch the existing Artik Engine scores; the composite is blended in
as the new 20% Intelligence factor at the app layer.
"""
from __future__ import annotations

import datetime as _dt


def _iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _label(score: float) -> str:
    return "Bullish" if score >= 60 else "Bearish" if score <= 40 else "Neutral"


def _i(d, k) -> int:
    try:
        return int(d.get(k) or 0)
    except (TypeError, ValueError):
        return 0


def _f(d, k):
    try:
        v = d.get(k)
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


_POS = ("beat", "surge", "soar", "record", "upgrade", "raise", "growth", "strong", "win",
        "approval", "outperform", "jump", "rally", "buyback", "expansion")
_NEG = ("miss", "plunge", "fall", "drop", "downgrade", "cut", "lawsuit", "probe", "recall",
        "weak", "loss", "decline", "warn", "investigation", "layoff", "bankruptcy")


def news_signal(news, sentiment) -> dict:
    articles = news if isinstance(news, list) else []
    ns = sentiment if isinstance(sentiment, dict) else {}
    bull = _f(ns.get("sentiment") or {}, "bullishPercent")
    bear = _f(ns.get("sentiment") or {}, "bearishPercent")
    pos = neg = neu = 0
    for a in articles:
        txt = f"{a.get('headline', '')} {a.get('summary', '')}".lower()
        p = sum(w in txt for w in _POS)
        n = sum(w in txt for w in _NEG)
        if p > n:
            pos += 1
        elif n > p:
            neg += 1
        else:
            neu += 1
    total = pos + neg + neu
    if bull is not None:
        score = round(bull * 100 if bull <= 1 else bull)
    elif total:
        score = round(50 + (pos - neg) / total * 50)
    else:
        score = 50
    top = sorted(articles, key=lambda a: a.get("datetime") or 0, reverse=True)[:6]
    return {
        "available": bool(articles or ns), "score": score, "signal": _label(score),
        "confidence": min(100, total * 4 or (30 if ns else 0)),
        "positive": pos, "negative": neg, "neutral": neu,
        "bullishPercent": bull, "bearishPercent": bear,
        "topHeadlines": [{"headline": a.get("headline"), "source": a.get("source"),
                          "url": a.get("url"), "datetime": a.get("datetime")} for a in top],
        "breaking": ({"headline": top[0].get("headline"), "url": top[0].get("url")} if top else None),
        "lastUpdated": (top[0].get("datetime") if top else None),
    }


def analyst_signal(recs) -> dict:
    recs = recs if isinstance(recs, list) else []
    if not recs:
        return {"available": False, "score": 50, "signal": "Neutral", "confidence": 0}
    cur, prev = recs[0], (recs[1] if len(recs) > 1 else {})
    sb, b, h, s, ss = (_i(cur, "strongBuy"), _i(cur, "buy"), _i(cur, "hold"),
                       _i(cur, "sell"), _i(cur, "strongSell"))
    total = sb + b + h + s + ss
    bull_w, bear_w = sb * 2 + b, s + ss * 2
    denom = max(bull_w + bear_w + h, 1)                     # normalize so score stays 0-100
    score = round(max(0, min(100, 50 + (bull_w - bear_w) / denom * 50)))
    mom = {k: _i(cur, k) - _i(prev, k) for k in ("strongBuy", "buy", "hold", "sell", "strongSell")}
    return {"available": True, "score": score, "signal": _label(score),
            "confidence": min(100, total * 5), "period": cur.get("period"),
            "strongBuy": sb, "buy": b, "hold": h, "sell": s, "strongSell": ss, "momChanges": mom}


def insider_signal(trans, sent) -> dict:
    txns = (trans or {}).get("data") if isinstance(trans, dict) else []
    txns = txns or []
    buys = [t for t in txns if str(t.get("transactionCode", "")).upper() == "P"]
    sells = [t for t in txns if str(t.get("transactionCode", "")).upper() == "S"]
    total_buy = sum(abs(_i(t, "change")) for t in buys)
    total_sell = sum(abs(_i(t, "change")) for t in sells)
    net = total_buy - total_sell
    sdata = (sent or {}).get("data") if isinstance(sent, dict) else []
    mspr = _f(sdata[-1], "mspr") if sdata else None
    score = 50
    if (total_buy + total_sell) > 0:
        score = 50 + net / (total_buy + total_sell) * 50
    if mspr is not None:
        score = (score + (50 + mspr / 2)) / 2
    score = round(max(0, min(100, score)))
    ceo = sum(1 for t in buys if "ceo" in str(t.get("name", "")).lower())
    director = sum(1 for t in buys if "director" in str(t.get("name", "")).lower())
    return {"available": bool(txns or sdata), "score": score, "signal": _label(score),
            "confidence": min(100, len(txns) * 8 + (20 if mspr is not None else 0)),
            "buys": len(buys), "sells": len(sells), "totalBuying": total_buy,
            "totalSelling": total_sell, "net": net, "mspr": mspr,
            "ceoPurchases": ceo, "directorPurchases": director}


def institutional_signal(fund) -> dict:
    own = []
    if isinstance(fund, dict):
        own = fund.get("ownership") or fund.get("data") or []
    inc = sum(1 for o in own if _i(o, "change") > 0)
    dec = sum(1 for o in own if _i(o, "change") < 0)
    net = sum(_i(o, "change") for o in own)
    trend = ("Accumulation" if net > 0 and inc >= dec else
             "Distribution" if net < 0 and dec > inc else "Neutral")
    score = 50 + (20 if trend == "Accumulation" else -20 if trend == "Distribution" else 0)
    top = sorted(own, key=lambda o: abs(_i(o, "change")), reverse=True)[:5]
    return {"available": bool(own), "score": score, "signal": _label(score),
            "confidence": min(100, len(own) * 5), "trend": trend,
            "increasing": inc, "decreasing": dec, "netShareChange": net,
            "topChanges": [{"name": o.get("name"), "change": _i(o, "change"),
                            "share": _i(o, "share")} for o in top]}


def sec_signal(filings) -> dict:
    fl = filings if isinstance(filings, list) else []

    def latest(prefix):
        return next((f for f in fl if str(f.get("form", "")).upper().startswith(prefix)), None)

    def slim(f):
        return None if not f else {"form": f.get("form"), "filedDate": f.get("filedDate"),
                                   "url": f.get("reportUrl") or f.get("filingUrl")}
    latest_map = {"10-K": slim(latest("10-K")), "10-Q": slim(latest("10-Q")),
                  "8-K": slim(latest("8-K")), "proxy": slim(latest("DEF 14A"))}
    recent = [slim(f) for f in fl[:6]]
    return {"available": bool(fl), "score": 50, "signal": "Neutral",
            "confidence": 40 if fl else 0, "latest": latest_map, "recent": recent}


def earnings_signal(surprises, calendar) -> dict:
    sur = surprises if isinstance(surprises, list) else []
    beats = sum(1 for s in sur if (_f(s, "surprisePercent") or 0) > 0)
    misses = sum(1 for s in sur if (_f(s, "surprisePercent") or 0) < 0)
    recent = sur[:4]
    vals = [_f(s, "surprisePercent") for s in recent if _f(s, "surprisePercent") is not None]
    avg = sum(vals) / len(vals) if vals else None
    score = round(max(0, min(100, 50 + avg * 2))) if avg is not None else 50
    cal = (calendar or {}).get("earningsCalendar") if isinstance(calendar, dict) else []
    nxt = (cal or [{}])[0]
    return {"available": bool(sur), "score": score, "signal": _label(score),
            "confidence": min(100, len(sur) * 12), "beats": beats, "misses": misses,
            "avgSurprisePct": round(avg, 1) if avg is not None else None,
            "nextDate": nxt.get("date") if isinstance(nxt, dict) else None,
            "recent": [{"period": s.get("period"), "actual": _f(s, "actual"),
                        "estimate": _f(s, "estimate"), "surprisePct": _f(s, "surprisePercent")}
                       for s in recent]}


_COMPOSITE_WEIGHTS = {"news": 0.20, "analyst": 0.22, "insider": 0.18,
                      "institutional": 0.15, "earnings": 0.15, "sec": 0.10}


def composite_signal(signals: dict) -> dict:
    tot = wsum = 0.0
    confs = []
    for k, w in _COMPOSITE_WEIGHTS.items():
        sig = signals.get(k) or {}
        if not sig.get("available"):
            continue
        tot += sig.get("score", 50) * w
        wsum += w
        confs.append(sig.get("confidence", 0))
    score = round(tot / wsum) if wsum else 50
    return {"score": score, "signal": _label(score),
            "confidence": round(sum(confs) / len(confs)) if confs else 0,
            "timestamp": _iso(), "coverage": round(wsum / sum(_COMPOSITE_WEIGHTS.values()) * 100)}


def build_intelligence(bundle: dict) -> dict:
    """Compute all signals + composite from a Finnhub bundle {data:{...}}."""
    d = (bundle or {}).get("data") or {}
    signals = {
        "news": news_signal(d.get("company_news"), d.get("news_sentiment")),
        "analyst": analyst_signal(d.get("recommendations")),
        "insider": insider_signal(d.get("insider_transactions"), d.get("insider_sentiment")),
        "institutional": institutional_signal(d.get("fund_ownership")),
        "sec": sec_signal(d.get("filings")),
        "earnings": earnings_signal(d.get("earnings"), d.get("earnings_calendar")),
    }
    signals["composite"] = composite_signal(signals)
    signals["esg"] = d.get("esg") if isinstance(d.get("esg"), dict) else None
    return signals
