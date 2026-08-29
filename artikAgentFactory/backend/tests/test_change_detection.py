from app.services.pipeline.change_detector import detect_changes
from app.services.pipeline.dedup import dedup, dedup_key
from app.templates.registry import get_template


class FakeResult:
    def __init__(self, dedup_key, title, first_seen_run_id, fields_json):
        self.dedup_key = dedup_key
        self.title = title
        self.first_seen_run_id = first_seen_run_id
        self.fields_json = fields_json


TEMPLATE = get_template("college_discovery")  # has application_deadline / estimated_cost tracked_for_changes


def test_new_result_marked_new_and_first_seen_set():
    candidates = dedup([{"url": "https://example.edu/x", "title": "X", "confidence_score": 0.9, "fields": {}}])
    deduped, counts = detect_changes({}, candidates, TEMPLATE, run_id=5)
    assert counts == {"new": 1, "changed": 0, "unchanged": 0}
    assert deduped[0]["_change_status"] == "new"
    assert deduped[0]["_first_seen_run_id"] == 5


def test_tracked_field_change_detected_and_untracked_ignored():
    key = dedup_key("https://example.edu/college-a")
    existing = {key: FakeResult(key, "College A", first_seen_run_id=1,
                                fields_json='{"application_deadline": "2026-01-01", "estimated_cost": "$60000", "untracked_note": "old note"}')}
    candidates = dedup([{
        "url": "https://example.edu/college-a", "title": "College A", "confidence_score": 0.9,
        "fields": {"application_deadline": "2026-01-15", "estimated_cost": "$60000", "untracked_note": "new note"},
    }])
    deduped, counts = detect_changes(existing, candidates, TEMPLATE, run_id=2)
    assert counts == {"new": 0, "changed": 1, "unchanged": 0}
    c = deduped[0]
    assert c["_change_status"] == "changed"
    assert c["_changed_fields"]["application_deadline"] == {"old": "2026-01-01", "new": "2026-01-15"}
    assert "estimated_cost" not in c["_changed_fields"]
    assert "untracked_note" not in c["_changed_fields"]  # not in template.result_fields[].tracked_for_changes
    assert c["_first_seen_run_id"] == 1  # preserved, not overwritten


def test_identical_fields_marked_unchanged_and_last_seen_bumped():
    key = dedup_key("https://example.edu/college-a")
    existing = {key: FakeResult(key, "College A", first_seen_run_id=1,
                                fields_json='{"application_deadline": "2026-01-15", "estimated_cost": "$60000"}')}
    candidates = dedup([{
        "url": "https://example.edu/college-a", "title": "College A", "confidence_score": 0.9,
        "fields": {"application_deadline": "2026-01-15", "estimated_cost": "$60000"},
    }])
    deduped, counts = detect_changes(existing, candidates, TEMPLATE, run_id=3)
    assert counts == {"new": 0, "changed": 0, "unchanged": 1}
    assert deduped[0]["_last_seen_run_id"] == 3
    assert deduped[0]["_first_seen_run_id"] == 1


def test_title_change_alone_counts_as_changed():
    key = dedup_key("https://example.edu/college-a")
    existing = {key: FakeResult(key, "Old Title", first_seen_run_id=1, fields_json="{}")}
    candidates = dedup([{"url": "https://example.edu/college-a", "title": "New Title", "confidence_score": 0.9, "fields": {}}])
    deduped, counts = detect_changes(existing, candidates, TEMPLATE, run_id=2)
    assert counts["changed"] == 1
    assert deduped[0]["_changed_fields"]["title"] == {"old": "Old Title", "new": "New Title"}
