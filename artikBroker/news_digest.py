"""Slack digest of the Stock News Collector's latest run.

Reads the collector's stored `classified_news.jsonl` + `signals.jsonl` (the same data
the Agent Results view uses), formats a concise, Slack-friendly summary — per-stock
sentiment, the key signal, and a source link, plus a "No material update." list for
tracked stocks with nothing — and posts it to the #artik-news Incoming Webhook named in
the `NEWS_DIGEST_SLACK_WEBHOOK` env var.

Timezone: America/Los_Angeles (DST handled automatically via zoneinfo; the `tzdata`
package is pinned so it resolves on the slim container). Read-only over the collector
data; every entry point returns instead of raising so it can never break an agent run.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except Exception:  # noqa: BLE001 — extremely old runtimes only
    ZoneInfo = None  # type: ignore

_TZ_NAME = os.environ.get("NEWS_DIGEST_TZ") or "America/Los_Angeles"
_EMOJI = {"positive": "🟢", "negative": "🔴", "neutral": "⚪"}
_MAX_FEATURED = 12          # keep the message concise / Slack-friendly
_MAX_NO_UPDATE = 45         # cap the "No material update" list length


def _now_tz() -> datetime:
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo(_TZ_NAME))
        except Exception:  # noqa: BLE001 — missing tzdata → fall back to naive local
            pass
    return datetime.now()


def _read_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _clean_source(raw: str | None) -> str:
    """'yfinance:GuruFocus.com' / 'google_news:Stock Titan' -> 'GuruFocus' / 'Stock Titan'."""
    parts = (raw or "").split(":", 1)
    label = (parts[1] if len(parts) > 1 else parts[0]).strip()
    return label.replace(".com", "").strip() or "source"


def _trim(headline: str, n: int = 110) -> str:
    h = (headline or "").strip()
    if len(h) <= n:
        return h
    return h[:n].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


def build_digest(data_dir, tracked: list[str] | None = None, *,
                 only: list[str] | set[str] | None = None, since_hours: float | None = 48,
                 title: str = "Stock News Collector — 24-Hour Digest") -> tuple[str | None, dict]:
    """Return (slack_text, stats). slack_text is None when there is no material news.

    `tracked`   — scopes the "No material update" list to these tickers.
    `only`      — restrict featured content to this ticker set (used for per-batch digests).
    `since_hours` — only consider headlines classified within this window (freshness; None = all).
    """
    data_dir = Path(data_dir)
    only_u = {str(t).strip().upper() for t in only} if only else None
    cutoff = None
    if since_hours:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _fresh(c: dict) -> bool:
        if cutoff is None:
            return True
        ts = c.get("classified_at") or ""
        return (not ts) or (ts >= cutoff)   # keep undated rows; ISO-8601 UTC compares lexically

    classified = [c for c in _read_jsonl(data_dir / "classified_news.jsonl")
                  if c.get("relevance") == "RELEVANT" and _fresh(c)]
    sigs = {s.get("id"): s for s in _read_jsonl(data_dir / "signals.jsonl")}

    # Highest-impact relevant headline per ticker (optionally restricted to `only`).
    best: dict[str, tuple[dict, dict]] = {}
    for c in classified:
        t = (c.get("ticker") or "").strip().upper()
        if not t or (only_u is not None and t not in only_u):
            continue
        sig = sigs.get(c.get("id")) or {}
        imp = sig.get("impact_score") or 0
        cur = best.get(t)
        if cur is None or imp > (cur[1].get("impact_score") or 0):
            best[t] = (c, sig)

    tracked_u = [str(t).strip().upper() for t in (tracked or []) if str(t).strip()]
    with_news = [t for t in tracked_u if t in best] if tracked_u else list(best)
    no_news = [t for t in tracked_u if t not in best] if tracked_u else []

    # Sentiment counts scoped to the fresh, in-scope headlines this digest covers.
    scoped_sigs = [sigs[c.get("id")] for c in classified
                   if (only_u is None or (c.get("ticker") or "").strip().upper() in only_u)
                   and c.get("id") in sigs]
    pos = sum(1 for s in scoped_sigs if s.get("sentiment") == "positive")
    neg = sum(1 for s in scoped_sigs if s.get("sentiment") == "negative")
    neu = max(0, len(scoped_sigs) - pos - neg)
    stats = {"tracked": len(tracked_u), "with_news": len(with_news), "no_news": len(no_news),
             "signals": len(scoped_sigs), "positive": pos, "negative": neg, "neutral": neu}

    if not best:
        return None, stats

    featured = sorted(best.items(), key=lambda kv: -(kv[1][1].get("impact_score") or 0))[:_MAX_FEATURED]
    now = _now_tz()
    lines = [
        f"📰 *{title}*",
        f"_As of {now.strftime('%b %-d, %Y · %-I:%M %p %Z').strip()} ({_TZ_NAME})_",
        (f"{stats['tracked']} tracked · {stats['with_news']} with news · "
         f"{stats['signals']} signals  ({pos} 🟢 / {neg} 🔴 / {neu} ⚪)"),
        "",
        "*🔝 Top updates*",
    ]
    for t, (c, sig) in featured:
        emo = _EMOJI.get(sig.get("sentiment"), "⚪")
        tag = f" _({sig.get('signal_type')})_" if sig.get("signal_type") else ""
        url = c.get("url") or ""
        link = f" · <{url}|{_clean_source(c.get('source'))}>" \
            if url.startswith(("http://", "https://")) else ""
        lines.append(f"{emo} *{t}* — {_trim(c.get('headline'))}{tag}{link}")

    if no_news:
        shown = ", ".join(no_news[:_MAX_NO_UPDATE])
        more = f" +{len(no_news) - _MAX_NO_UPDATE} more" if len(no_news) > _MAX_NO_UPDATE else ""
        lines += ["", f"*No material update:* {shown}{more}"]

    lines.append("_via Stock News Collector · trusted-source news + signal classification_")
    return "\n".join(lines), stats


def post_to_slack(text: str, webhook: str | None = None) -> tuple[bool, str]:
    """POST {text} to a Slack Incoming Webhook. Returns (ok, detail); never raises."""
    webhook = (webhook or os.environ.get("NEWS_DIGEST_SLACK_WEBHOOK") or "").strip()
    if not webhook:
        return False, "no NEWS_DIGEST_SLACK_WEBHOOK configured"
    try:
        req = urllib.request.Request(
            webhook, data=json.dumps({"text": text}).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return (200 <= r.status < 300), f"http {r.status}"
    except urllib.error.HTTPError as e:
        return False, f"http {e.code}: {e.read().decode('utf-8', 'replace')[:120]}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def build_and_post(data_dir, tracked: list[str] | None = None,
                   webhook: str | None = None, **kw) -> tuple[bool, str, dict]:
    """Build the digest and post it. Returns (ok, detail, stats)."""
    text, stats = build_digest(data_dir, tracked, **kw)
    if not text:
        return False, "no material news to post", stats
    ok, detail = post_to_slack(text, webhook)
    return ok, detail, stats
