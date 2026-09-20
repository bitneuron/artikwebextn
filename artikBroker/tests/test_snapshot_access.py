"""Ownership rules for portfolio snapshots (_snapshot_visible).

The guard this replaces read `if u and ...`, so it did nothing when no user was
resolved, and it treated a snapshot with no user_id as visible to everyone.
"""
from __future__ import annotations

import types

import app


def _req(user):
    r = types.SimpleNamespace()
    r.state = types.SimpleNamespace(user=user)
    return r


ADMIN = {"id": 1, "role": "admin"}
ALICE = {"id": 2, "role": "user"}
BOB = {"id": 3, "role": "user"}


def test_owner_can_see_their_own_snapshot():
    assert app._snapshot_visible(_req(ALICE), {"user_id": 2}) is True


def test_other_user_cannot_see_someone_elses_snapshot():
    assert app._snapshot_visible(_req(BOB), {"user_id": 2}) is False


def test_admin_can_see_any_snapshot():
    assert app._snapshot_visible(_req(ADMIN), {"user_id": 2}) is True


def test_anonymous_request_is_refused(monkeypatch):
    # Fails closed. Previously `if u and ...` skipped the check entirely here.
    monkeypatch.setattr(app, "OPEN_MODE", False)
    assert app._snapshot_visible(_req(None), {"user_id": 2}) is False


def test_ownerless_snapshot_is_admin_only(monkeypatch):
    # "unowned" must not mean "everyone's".
    monkeypatch.setattr(app, "OPEN_MODE", False)
    assert app._snapshot_visible(_req(ALICE), {"user_id": None}) is False
    assert app._snapshot_visible(_req(ADMIN), {"user_id": None}) is True


def test_internal_calls_pass_no_request():
    assert app._snapshot_visible(None, {"user_id": 99}) is True


def test_open_mode_is_dev_only_and_permits(monkeypatch):
    monkeypatch.setattr(app, "OPEN_MODE", True)
    assert app._snapshot_visible(_req(None), {"user_id": 2}) is True
