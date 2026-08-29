"""SQLite drops tzinfo on every DateTime(timezone=True) column when the value comes
back out of the database — even though every write goes in via `_utcnow()`
(timezone-aware UTC), reads return a naive datetime. FastAPI's JSON encoder then
serializes it without a 'Z'/offset (e.g. "2026-08-29T22:08:19"), and browsers parse
an offset-less ISO datetime-with-time as LOCAL time, not UTC — so every timestamp in
the UI silently renders shifted by the viewer's UTC offset. Postgres (staging/prod)
does not have this bug, but reattaching UTC when tzinfo is missing is a no-op there,
so this type is safe on both backends."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:  # noqa: ANN001
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value
