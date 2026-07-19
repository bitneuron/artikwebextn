"""SQLite metadata store for ArtikResearch (papers, journals, analyses, chats, versions).

Structured extraction ("knowledge graphs") + journal profiles are stored as JSON here; the
actual files live on the filesystem under uploads/ and generated/. This is the iteration-1
persistence layer — Postgres + pgvector/ChromaDB slot in behind the same functions.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

from .config import DB_PATH

_lock = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _id() -> str:
    return uuid.uuid4().hex[:16]


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH), timeout=10, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=5000")
    return c


def init() -> None:
    with _lock, _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS papers (
          id TEXT PRIMARY KEY, name TEXT, filename TEXT, path TEXT, fmt TEXT,
          target_journal TEXT, output_format TEXT DEFAULT 'docx',
          status TEXT DEFAULT 'uploaded', readiness INTEGER,
          knowledge_json TEXT, summary TEXT, created_at TEXT, updated_at TEXT, deleted_at TEXT);
        CREATE TABLE IF NOT EXISTS journals (
          id TEXT PRIMARY KEY, name TEXT, source TEXT DEFAULT 'upload',
          profile_json TEXT, files_json TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS analyses (
          id TEXT PRIMARY KEY, paper_id TEXT, journal TEXT, kind TEXT,
          result_json TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS chats (
          id TEXT PRIMARY KEY, paper_id TEXT, role TEXT, content TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS versions (
          id TEXT PRIMARY KEY, paper_id TEXT, label TEXT, content TEXT, created_at TEXT);
        """)
        # Migration: add output_format to pre-existing paper rows.
        cols = {r[1] for r in c.execute("PRAGMA table_info(papers)")}
        if "output_format" not in cols:
            c.execute("ALTER TABLE papers ADD COLUMN output_format TEXT DEFAULT 'docx'")


# ── papers ────────────────────────────────────────────────────────────────────
def add_paper(name, filename, path, fmt) -> dict:
    init()
    pid = _id()
    with _lock, _conn() as c:
        c.execute("INSERT INTO papers (id,name,filename,path,fmt,status,created_at,updated_at) "
                  "VALUES (?,?,?,?,?,?,?,?)", (pid, name, filename, path, fmt, "uploaded", _now(), _now()))
    return get_paper(pid)


def get_paper(pid) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM papers WHERE id=? AND deleted_at IS NULL", (pid,)).fetchone()
    return _paper_row(r) if r else None


def list_papers() -> list[dict]:
    init()
    with _conn() as c:
        return [_paper_row(r) for r in c.execute(
            "SELECT * FROM papers WHERE deleted_at IS NULL ORDER BY updated_at DESC").fetchall()]


def update_paper(pid, **fields) -> dict | None:
    if not fields:
        return get_paper(pid)
    sets, args = [], []
    for k, v in fields.items():
        if k in ("knowledge",):
            k, v = "knowledge_json", json.dumps(v)
        sets.append(f"{k}=?")
        args.append(v)
    sets.append("updated_at=?")
    args.append(_now())
    with _lock, _conn() as c:
        c.execute(f"UPDATE papers SET {', '.join(sets)} WHERE id=?", args + [pid])
    return get_paper(pid)


def delete_paper(pid) -> None:
    with _lock, _conn() as c:
        c.execute("UPDATE papers SET deleted_at=? WHERE id=?", (_now(), pid))


def _paper_row(r) -> dict:
    d = dict(r)
    d["knowledge"] = json.loads(d.pop("knowledge_json") or "null")
    d.pop("deleted_at", None)
    return d


# ── journals ──────────────────────────────────────────────────────────────────
def upsert_journal(name, profile, source="upload", files=None) -> dict:
    init()
    with _lock, _conn() as c:
        existing = c.execute("SELECT id FROM journals WHERE LOWER(name)=LOWER(?)", (name,)).fetchone()
        if existing:
            jid = existing["id"]
            c.execute("UPDATE journals SET profile_json=?, files_json=?, updated_at=? WHERE id=?",
                      (json.dumps(profile), json.dumps(files or []), _now(), jid))
        else:
            jid = _id()
            c.execute("INSERT INTO journals (id,name,source,profile_json,files_json,created_at,updated_at) "
                      "VALUES (?,?,?,?,?,?,?)",
                      (jid, name, source, json.dumps(profile), json.dumps(files or []), _now(), _now()))
    return get_journal(jid)


def get_journal(jid) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM journals WHERE id=?", (jid,)).fetchone()
    return _journal_row(r) if r else None


def get_journal_by_name(name) -> dict | None:
    init()
    with _conn() as c:
        r = c.execute("SELECT * FROM journals WHERE LOWER(name)=LOWER(?)", (name,)).fetchone()
    return _journal_row(r) if r else None


def list_journals() -> list[dict]:
    init()
    with _conn() as c:
        return [_journal_row(r) for r in c.execute(
            "SELECT * FROM journals ORDER BY name").fetchall()]


def _journal_row(r) -> dict:
    d = dict(r)
    d["profile"] = json.loads(d.pop("profile_json") or "{}")
    d["files"] = json.loads(d.pop("files_json") or "[]")
    return d


# ── analyses / chats / versions ───────────────────────────────────────────────
def add_analysis(paper_id, journal, kind, result) -> dict:
    init()
    aid = _id()
    with _lock, _conn() as c:
        c.execute("INSERT INTO analyses (id,paper_id,journal,kind,result_json,created_at) "
                  "VALUES (?,?,?,?,?,?)", (aid, paper_id, journal, kind, json.dumps(result), _now()))
    return {"id": aid, "paper_id": paper_id, "journal": journal, "kind": kind,
            "result": result, "created_at": _now()}


def list_analyses(paper_id, kind=None) -> list[dict]:
    with _conn() as c:
        q = "SELECT * FROM analyses WHERE paper_id=?"
        args = [paper_id]
        if kind:
            q += " AND kind=?"
            args.append(kind)
        q += " ORDER BY created_at DESC"
        rows = c.execute(q, args).fetchall()
    return [{**dict(r), "result": json.loads(r["result_json"] or "null")} for r in rows]


def latest_analysis(paper_id, kind) -> dict | None:
    a = list_analyses(paper_id, kind)
    return a[0] if a else None


def add_chat(paper_id, role, content) -> None:
    init()
    with _lock, _conn() as c:
        c.execute("INSERT INTO chats (id,paper_id,role,content,created_at) VALUES (?,?,?,?,?)",
                  (_id(), paper_id, role, content, _now()))


def list_chats(paper_id, limit=50) -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT role,content,created_at FROM chats WHERE paper_id=? "
                         "ORDER BY created_at LIMIT ?", (paper_id, limit)).fetchall()
    return [dict(r) for r in rows]


def add_version(paper_id, label, content) -> dict:
    init()
    vid = _id()
    with _lock, _conn() as c:
        c.execute("INSERT INTO versions (id,paper_id,label,content,created_at) VALUES (?,?,?,?,?)",
                  (vid, paper_id, label, content, _now()))
    return {"id": vid, "paper_id": paper_id, "label": label, "created_at": _now()}


def list_versions(paper_id) -> list[dict]:
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT id,label,created_at FROM versions WHERE paper_id=? ORDER BY created_at DESC",
            (paper_id,)).fetchall()]


def get_version(vid) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM versions WHERE id=?", (vid,)).fetchone()
    return dict(r) if r else None
