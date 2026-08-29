"""Stage 4 — URL-only dedup key, not title-based (LLM-written titles vary run to run
for the same underlying page)."""
from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def normalize_url(url: str) -> str:
    try:
        parts = urlsplit(url.strip())
        netloc = parts.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = parts.path.rstrip("/")
        query_pairs = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                       if not k.lower().startswith("utm_")]
        query = urlencode(query_pairs)
        return urlunsplit((parts.scheme.lower() or "https", netloc, path, query, ""))
    except Exception:  # noqa: BLE001
        return url.strip().lower()


def dedup_key(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode()).hexdigest()


def dedup(candidates: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for c in candidates:
        url = (c.get("url") or "").strip()
        if not url:
            continue
        key = dedup_key(url)
        c["_dedup_key"] = key
        existing = best.get(key)
        if not existing or (c.get("confidence_score") or 0) > (existing.get("confidence_score") or 0):
            best[key] = c
    return list(best.values())
