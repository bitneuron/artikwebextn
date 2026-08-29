"""JSON (de)serialization helpers for TEXT-backed JSON columns (portable across
SQLite/Postgres — no dependency on a JSON column type)."""
from __future__ import annotations

import json


def to_json(value) -> str:
    return json.dumps(value if value is not None else {})


def from_json(value: str | None, default=None):
    if not value:
        return default if default is not None else {}
    try:
        return json.loads(value)
    except Exception:  # noqa: BLE001
        return default if default is not None else {}
