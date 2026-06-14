"""Server-side search-history store.

Backend is chosen by environment:
  * HISTORY_S3_BUCKET set  -> Amazon S3   (used on AWS; survives redeploys + shared across instances/devices)
  * otherwise              -> local folder artikBroker/search_history/  (dev)

Each search is one JSON document: {id, ts, type, query, summary, provider, count, results}.
`ts` is epoch-ms. Listing returns metadata only (no heavy `results`). Capped at
MAX_ENTRIES (oldest pruned on save). All operations degrade gracefully.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

HERE = Path(__file__).resolve().parent
MAX_ENTRIES = 50

_BUCKET = os.environ.get("HISTORY_S3_BUCKET", "").strip()
_PREFIX = (os.environ.get("HISTORY_S3_PREFIX", "search_history/") or "").strip()
_REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-west-2"
_LOCAL_DIR = HERE / "search_history"

_META_KEYS = ("id", "ts", "type", "query", "summary", "provider", "count")


def backend() -> str:
    return "s3" if _BUCKET else "local"


def _new_id() -> str:
    return f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"


def _meta(e: dict) -> dict:
    return {k: e.get(k) for k in _META_KEYS}


# ── S3 backend ────────────────────────────────────────────────────────────────
_s3 = None


def _client():
    global _s3
    if _s3 is None:
        import boto3  # imported lazily so local dev needs no AWS deps
        _s3 = boto3.client("s3", region_name=_REGION)
    return _s3


def _s3_key(eid: str) -> str:
    return f"{_PREFIX}{eid}.json"


def _s3_save(e: dict) -> None:
    _client().put_object(Bucket=_BUCKET, Key=_s3_key(e["id"]),
                         Body=json.dumps(e).encode(), ContentType="application/json")


def _s3_get(eid: str):
    try:
        obj = _client().get_object(Bucket=_BUCKET, Key=_s3_key(eid))
        return json.loads(obj["Body"].read())
    except Exception:  # noqa: BLE001
        return None


def _s3_delete(eid: str) -> None:
    try:
        _client().delete_object(Bucket=_BUCKET, Key=_s3_key(eid))
    except Exception:  # noqa: BLE001
        pass


def _s3_all() -> list:
    keys, token = [], None
    while True:
        kw = {"Bucket": _BUCKET, "Prefix": _PREFIX}
        if token:
            kw["ContinuationToken"] = token
        try:
            r = _client().list_objects_v2(**kw)
        except Exception:  # noqa: BLE001
            return []
        keys += [o["Key"] for o in r.get("Contents", []) if o["Key"].endswith(".json")]
        if not r.get("IsTruncated"):
            break
        token = r.get("NextContinuationToken")

    def rd(k):
        try:
            return json.loads(_client().get_object(Bucket=_BUCKET, Key=k)["Body"].read())
        except Exception:  # noqa: BLE001
            return None

    with ThreadPoolExecutor(max_workers=8) as ex:
        return [e for e in ex.map(rd, keys) if e]


# ── Local backend ───────────────────────────────────────────────────────────--
def _local_path(eid: str) -> Path:
    return _LOCAL_DIR / f"{eid}.json"


def _local_save(e: dict) -> None:
    _LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    _local_path(e["id"]).write_text(json.dumps(e))


def _local_get(eid: str):
    p = _local_path(eid)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return None


def _local_delete(eid: str) -> None:
    try:
        _local_path(eid).unlink()
    except FileNotFoundError:
        pass


def _local_all() -> list:
    if not _LOCAL_DIR.is_dir():
        return []
    out = []
    for p in _LOCAL_DIR.glob("*.json"):
        try:
            out.append(json.loads(p.read_text()))
        except Exception:  # noqa: BLE001
            pass
    return out


# ── Public API (dispatches to the active backend) ──────────────────────────────
def _all() -> list:
    return _s3_all() if _BUCKET else _local_all()


def save(entry: dict) -> dict:
    e = {
        "id": _new_id(),
        "ts": int(time.time() * 1000),
        "type": entry.get("type"),
        "query": entry.get("query") or "",
        "summary": entry.get("summary"),
        "provider": entry.get("provider"),
        "count": entry.get("count"),
        "results": entry.get("results") or [],
    }
    (_s3_save if _BUCKET else _local_save)(e)
    _prune()
    return {"id": e["id"], "ts": e["ts"]}


def list_meta(limit: int = MAX_ENTRIES) -> list:
    alle = _all()
    alle.sort(key=lambda e: e.get("ts", 0), reverse=True)
    return [_meta(e) for e in alle[:limit]]


def get(eid: str):
    return _s3_get(eid) if _BUCKET else _local_get(eid)


def delete(eid: str) -> None:
    (_s3_delete if _BUCKET else _local_delete)(eid)


def delete_many(ids) -> int:
    n = 0
    for eid in ids:
        if eid:
            delete(str(eid))
            n += 1
    return n


def clear() -> None:
    for e in _all():
        delete(e["id"])


def _prune() -> None:
    alle = _all()
    if len(alle) <= MAX_ENTRIES:
        return
    alle.sort(key=lambda e: e.get("ts", 0), reverse=True)
    for e in alle[MAX_ENTRIES:]:
        delete(e["id"])
