"""Search history is per user.

A query reveals what someone is researching and the delete is unrecoverable, so
every read and write is scoped to its owner. Before this, one global store was
readable, and wipeable, by any signed-in user.
"""
from __future__ import annotations

import history_store as hist


ALICE, BOB = 2, 3


def _fresh(tmp_path, monkeypatch):
    """Point the local backend at a temp dir; never touch the real store."""
    monkeypatch.setattr(hist, "_BUCKET", "")
    monkeypatch.setattr(hist, "_LOCAL_DIR", tmp_path)
    return tmp_path


def test_each_user_sees_only_their_own(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    hist.save({"query": "alice idea"}, user_id=ALICE)
    hist.save({"query": "bob idea"}, user_id=BOB)
    assert [e["query"] for e in hist.list_meta(ALICE)] == ["alice idea"]
    assert [e["query"] for e in hist.list_meta(BOB)] == ["bob idea"]


def test_admin_sees_everything(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    hist.save({"query": "alice idea"}, user_id=ALICE)
    hist.save({"query": "bob idea"}, user_id=BOB)
    assert len(hist.list_meta(999, is_admin=True)) == 2


def test_fetching_someone_elses_entry_returns_nothing(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    eid = hist.save({"query": "alice idea"}, user_id=ALICE)["id"]
    assert hist.get(eid, ALICE) is not None
    assert hist.get(eid, BOB) is None            # same answer as "does not exist"


def test_deleting_someone_elses_entry_is_refused(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    eid = hist.save({"query": "alice idea"}, user_id=ALICE)["id"]
    assert hist.delete(eid, BOB) is False
    assert hist.get(eid, ALICE) is not None      # still there
    assert hist.delete(eid, ALICE) is True


def test_bulk_delete_only_removes_your_own(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    a = hist.save({"query": "a"}, user_id=ALICE)["id"]
    b = hist.save({"query": "b"}, user_id=BOB)["id"]
    assert hist.delete_many([a, b], BOB) == 1    # only bob's
    assert hist.get(a, ALICE) is not None


def test_clear_does_not_wipe_other_users(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    hist.save({"query": "a1"}, user_id=ALICE)
    hist.save({"query": "a2"}, user_id=ALICE)
    hist.save({"query": "b1"}, user_id=BOB)
    assert hist.clear(ALICE) == 2
    assert [e["query"] for e in hist.list_meta(BOB)] == ["b1"]


def test_legacy_unowned_entries_are_admin_only(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    hist.save({"query": "from before owners existed"}, user_id=None)
    assert hist.list_meta(ALICE) == []
    assert len(hist.list_meta(None, is_admin=True)) == 1


def test_an_anonymous_caller_sees_nothing(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    hist.save({"query": "alice idea"}, user_id=ALICE)
    assert hist.list_meta(None) == []            # fails closed


def test_pruning_is_per_owner(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    monkeypatch.setattr(hist, "MAX_ENTRIES", 3)
    for i in range(5):
        hist.save({"query": f"a{i}"}, user_id=ALICE)
    hist.save({"query": "b1"}, user_id=BOB)
    # Alice's overflow must not evict Bob.
    assert len(hist.list_meta(ALICE)) == 3
    assert [e["query"] for e in hist.list_meta(BOB)] == ["b1"]
