"""In-memory login brute-force throttle — ported from artikBroker's
`_login_locked`/`_login_record_failure`/`_login_clear` (app.py:360-409). Keyed by
client IP AND identifier so neither a single IP spraying accounts nor a distributed
guess against one account gets unlimited tries. Single-instance service; fine for
this app's current scale (an AWS multi-instance deployment would need this moved to
a shared store like ElastiCache — not needed at this stage)."""
from __future__ import annotations

import time

_LOGIN_FAILS: dict[str, dict] = {}
LOGIN_MAX_ATTEMPTS = 5
LOGIN_BASE_LOCK_SECONDS = 30
LOGIN_MAX_LOCK_SECONDS = 900


def _keys(ip: str, identifier: str) -> list[str]:
    return [f"ip:{ip}", f"id:{(identifier or '').lower()}"]


def seconds_locked(ip: str, identifier: str) -> int:
    """Seconds remaining if locked out (max across the IP + identifier keys), else 0."""
    now = time.time()
    worst = 0
    for k in _keys(ip, identifier):
        rec = _LOGIN_FAILS.get(k)
        if rec and rec["count"] >= LOGIN_MAX_ATTEMPTS and rec["until"] > now:
            worst = max(worst, int(rec["until"] - now) + 1)
    return worst


def record_failure(ip: str, identifier: str) -> None:
    now = time.time()
    for k in _keys(ip, identifier):
        rec = _LOGIN_FAILS.get(k) or {"count": 0, "until": 0}
        rec["count"] += 1
        if rec["count"] >= LOGIN_MAX_ATTEMPTS:
            lock = min(LOGIN_BASE_LOCK_SECONDS * (2 ** (rec["count"] - LOGIN_MAX_ATTEMPTS)), LOGIN_MAX_LOCK_SECONDS)
            rec["until"] = now + lock
        _LOGIN_FAILS[k] = rec
    if len(_LOGIN_FAILS) > 4096:  # opportunistic cleanup, prevents unbounded growth
        for k in [k for k, v in _LOGIN_FAILS.items() if v["until"] < now and v["count"] < LOGIN_MAX_ATTEMPTS]:
            _LOGIN_FAILS.pop(k, None)


def clear(ip: str, identifier: str) -> None:
    for k in _keys(ip, identifier):
        _LOGIN_FAILS.pop(k, None)
