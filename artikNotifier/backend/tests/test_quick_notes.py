"""Quick Notes tests: CRUD, lifecycle, search/filter/sort, tags, reminder conversion,
chatbot integration, and security (auth + IDOR + audit)."""
from __future__ import annotations

from app.core.database import SessionLocal
from app.models.system import AuditLog


def _reg(client, email, pw="password123"):
    r = client.post("/api/auth/register", json={"email": email, "password": pw, "full_name": "X"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _note(client, h, **kw):
    body = {"note_text": "Pay property tax", "category": "Finance", "tags": ["Finance", "Tax"]}
    body.update(kw)
    r = client.post("/api/notes", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


# ── CRUD ──────────────────────────────────────────────────────────────────────
def test_create_minimal_note(client):
    h = _reg(client, "a@x.com")
    r = client.post("/api/notes", headers=h, json={"note_text": "Buy milk"})
    assert r.status_code == 201
    n = r.json()
    assert n["note_text"] == "Buy milk"
    assert n["status"] == "active" and n["category"] == "Personal"
    assert n["title"] is None and n["reminder_id"] is None


def test_note_text_required(client):
    h = _reg(client, "a@x.com")
    assert client.post("/api/notes", headers=h, json={"title": "no body"}).status_code == 422
    assert client.post("/api/notes", headers=h, json={"note_text": ""}).status_code == 422


def test_update_and_get_note(client):
    h = _reg(client, "a@x.com")
    n = _note(client, h)
    r = client.put(f"/api/notes/{n['id']}", headers=h, json={"title": "Tax!", "tags": ["Tax"]})
    assert r.status_code == 200
    got = client.get(f"/api/notes/{n['id']}", headers=h).json()
    assert got["title"] == "Tax!" and got["tags"] == ["Tax"]


def test_invalid_due_time_rejected(client):
    h = _reg(client, "a@x.com")
    assert client.post("/api/notes", headers=h,
                       json={"note_text": "x", "due_time": "9am"}).status_code == 422


# ── lifecycle ───────────────────────────────────────────────────────────────────
def test_complete_archive_restore_delete(client):
    h = _reg(client, "a@x.com")
    n = _note(client, h)
    nid = n["id"]
    assert client.post(f"/api/notes/{nid}/complete", headers=h).json()["status"] == "completed"
    arch = client.post(f"/api/notes/{nid}/archive", headers=h).json()
    assert arch["status"] == "archived" and arch["archived"] is True
    assert client.post(f"/api/notes/{nid}/restore", headers=h).json()["status"] == "active"
    assert client.delete(f"/api/notes/{nid}", headers=h).status_code == 200
    # soft-deleted → no longer retrievable / not in default list
    assert client.get(f"/api/notes/{nid}", headers=h).status_code == 404
    assert all(x["id"] != nid for x in client.get("/api/notes", headers=h).json())


# ── search / filter / sort ──────────────────────────────────────────────────────
def test_search_filter_sort(client):
    h = _reg(client, "a@x.com")
    _note(client, h, note_text="Mortgage payment due", category="Finance", tags=["Mortgage"])
    _note(client, h, note_text="Call insurance company", category="Medical", tags=["Insurance"])
    _note(client, h, note_text="Grocery list", category="Shopping", tags=["Shopping"])

    assert len(client.get("/api/notes?search=mortgage", headers=h).json()) == 1
    assert len(client.get("/api/notes?category=Finance", headers=h).json()) == 1
    assert len(client.get("/api/notes?tag=Insurance", headers=h).json()) == 1
    # tag search also matches the tag name via free-text
    assert len(client.get("/api/notes?search=shopping", headers=h).json()) >= 1
    # sort alphabetical by title falls back gracefully; sort by created works
    rows = client.get("/api/notes?sort=created_at&order=asc", headers=h).json()
    assert rows[0]["note_text"] == "Mortgage payment due"


# ── reminder conversion ─────────────────────────────────────────────────────────
def test_convert_to_reminder_copies_and_links(client):
    h = _reg(client, "a@x.com")
    n = _note(client, h, title="Property tax", due_date="2026-07-15", due_time="14:00",
              priority="high")
    r = client.post(f"/api/notes/{n['id']}/convert", headers=h)
    assert r.status_code == 200
    rid = r.json()["reminder_id"]
    assert r.json()["note"]["reminder_id"] == rid     # linked back, note preserved

    rem = client.get(f"/api/reminders/{rid}", headers=h).json()
    assert rem["title"] == "Property tax"
    assert rem["category"] == "Finance" and rem["priority"] == "high"
    assert set(rem["tags"]) == {"Finance", "Tax"}
    assert rem["due_at"].startswith("2026-07-15")
    # original note still exists
    assert client.get(f"/api/notes/{n['id']}", headers=h).status_code == 200


def test_convert_without_due_date_defaults(client):
    h = _reg(client, "a@x.com")
    n = _note(client, h, note_text="Idea: write a book", category="Ideas", tags=[])
    r = client.post(f"/api/notes/{n['id']}/convert", headers=h)
    assert r.status_code == 200
    rem = client.get(f"/api/reminders/{r.json()['reminder_id']}", headers=h).json()
    assert rem["due_at"]  # a sensible default due date was assigned


# ── chatbot integration ─────────────────────────────────────────────────────────
def test_chatbot_searches_notes(client):
    h = _reg(client, "a@x.com")
    _note(client, h, note_text="Mortgage refinance research", category="Finance", tags=["Mortgage"])
    _note(client, h, note_text="Buy running shoes", category="Shopping", tags=["Shopping"])

    fin = client.post("/api/assistant/chat", headers=h, json={"message": "show my finance notes"}).json()
    assert "Finance note" in fin["reply"]

    search = client.post("/api/assistant/chat", headers=h, json={"message": "search mortgage notes"}).json()
    assert "Mortgage" in search["reply"] or "mortgage" in search["reply"].lower()

    none = client.post("/api/assistant/chat", headers=h, json={"message": "show overdue notes"}).json()
    assert "overdue" in none["reply"].lower()


# ── security: auth + IDOR + audit ───────────────────────────────────────────────
def test_notes_require_auth(client):
    assert client.get("/api/notes").status_code == 401
    assert client.post("/api/notes", json={"note_text": "x"}).status_code == 401


def test_idor_notes_isolated_between_users(client):
    a = _reg(client, "alice@x.com")
    b = _reg(client, "bob@x.com")
    nid = _note(client, a, note_text="Alice-only secret note")["id"]

    # Bob cannot read / edit / delete / act on / convert Alice's note
    assert client.get(f"/api/notes/{nid}", headers=b).status_code == 404
    assert client.put(f"/api/notes/{nid}", headers=b, json={"title": "hax"}).status_code == 404
    assert client.delete(f"/api/notes/{nid}", headers=b).status_code == 404
    assert client.post(f"/api/notes/{nid}/complete", headers=b).status_code == 404
    assert client.post(f"/api/notes/{nid}/convert", headers=b).status_code == 404
    # Bob's list and assistant never surface Alice's note
    assert all("Alice" not in x["note_text"] for x in client.get("/api/notes", headers=b).json())
    reply = client.post("/api/assistant/chat", headers=b, json={"message": "show all notes"}).json()["reply"]
    assert "Alice-only secret" not in reply


def test_note_actions_are_audited(client):
    h = _reg(client, "a@x.com")
    n = _note(client, h)
    client.post(f"/api/notes/{n['id']}/convert", headers=h)
    db = SessionLocal()
    try:
        actions = {a.action for a in db.query(AuditLog).filter(AuditLog.entity == "quick_note").all()}
        assert {"note.create", "note.convert"} <= actions
    finally:
        db.close()


def test_invalid_note_id_safe(client):
    h = _reg(client, "a@x.com")
    assert client.get("/api/notes/999999", headers=h).status_code == 404
    assert client.get("/api/notes/1%20OR%201=1", headers=h).status_code == 422
