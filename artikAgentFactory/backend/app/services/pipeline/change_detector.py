"""Stage 5 — compares this run's deduped candidates against the agent's existing
(non-dismissed) Results, keyed by dedup_key. Mutates each candidate dict in place with
_change_status / _first_seen_run_id / _last_seen_run_id / _changed_fields."""
from __future__ import annotations

from app.core.utils import from_json
from app.models.result import Result
from app.templates.spec import TemplateSpec


def detect_changes(existing_by_key: dict[str, Result], deduped: list[dict],
                    template: TemplateSpec, run_id: int) -> tuple[list[dict], dict]:
    tracked_keys = [f.key for f in template.result_fields if f.tracked_for_changes]
    counts = {"new": 0, "changed": 0, "unchanged": 0}

    for c in deduped:
        key = c["_dedup_key"]
        existing = existing_by_key.get(key)
        c["_last_seen_run_id"] = run_id

        if not existing:
            c["_change_status"] = "new"
            c["_first_seen_run_id"] = run_id
            counts["new"] += 1
            continue

        c["_first_seen_run_id"] = existing.first_seen_run_id or run_id
        changed_fields: dict = {}
        if (existing.title or "") != (c.get("title") or ""):
            changed_fields["title"] = {"old": existing.title, "new": c.get("title")}

        existing_fields = from_json(existing.fields_json, {})
        new_fields = c.get("fields") or {}
        for tk in tracked_keys:
            old_v, new_v = existing_fields.get(tk), new_fields.get(tk)
            if str(old_v or "") != str(new_v or ""):
                changed_fields[tk] = {"old": old_v, "new": new_v}

        if changed_fields:
            c["_change_status"] = "changed"
            c["_changed_fields"] = changed_fields
            counts["changed"] += 1
        else:
            c["_change_status"] = "unchanged"
            counts["unchanged"] += 1

    return deduped, counts
