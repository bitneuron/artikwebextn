from __future__ import annotations

from datetime import datetime, timezone


def parse_date(value) -> datetime | None:
    """Best-effort parse of whatever date string the LLM emitted. Returns None (never
    raises) on anything unparseable — a missing date is common and not an error."""
    if not value or isinstance(value, (int, float, bool)):
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        pass
    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except Exception:  # noqa: BLE001
            continue
    return None
