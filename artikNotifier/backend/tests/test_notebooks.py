"""Notebooks + notes-first tests: notebook CRUD, note→notebook assignment, favorites,
integrated reminders (repeat), notebook filtering, delete-rehomes-notes, and migration."""
from __future__ import annotations


def _reg(client, email, pw="password123"):
    r = client.post("/api/auth/register", json={"email": email, "password": pw, "full_name": "X"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_default_notebook_autocreated_on_note(client):
    h = _reg(client, "nb1@x.com")
    n = client.post("/api/notes", headers=h, json={"note_text": "First note"}).json()
    assert n["notebook_id"] is not None          # note lands in a notebook
    nbs = client.get("/api/notebooks", headers=h).json()
    assert any(x["is_default"] and x["id"] == n["notebook_id"] for x in nbs)


def test_notebook_crud(client):
    h = _reg(client, "nb2@x.com")
    nb = client.post("/api/notebooks", headers=h, json={"name": "Finance", "icon": "💰"}).json()
    assert nb["name"] == "Finance" and nb["icon"] == "💰"
    # rename + favorite
    r = client.put(f"/api/notebooks/{nb['id']}", headers=h, json={"name": "Money", "is_favorite": True})
    assert r.status_code == 200 and r.json()["name"] == "Money" and r.json()["is_favorite"] is True
    # note count reflected
    client.post("/api/notes", headers=h, json={"note_text": "Budget", "notebook_id": nb["id"]})
    got = next(x for x in client.get("/api/notebooks", headers=h).json() if x["id"] == nb["id"])
    assert got["note_count"] == 1


def test_note_in_notebook_and_filter(client):
    h = _reg(client, "nb3@x.com")
    fin = client.post("/api/notebooks", headers=h, json={"name": "Finance"}).json()
    med = client.post("/api/notebooks", headers=h, json={"name": "Medical"}).json()
    client.post("/api/notes", headers=h, json={"note_text": "Tax", "notebook_id": fin["id"]})
    client.post("/api/notes", headers=h, json={"note_text": "Checkup", "notebook_id": med["id"]})
    fin_notes = client.get(f"/api/notes?notebook_id={fin['id']}", headers=h).json()
    assert len(fin_notes) == 1 and fin_notes[0]["note_text"] == "Tax"


def test_favorite_and_reminder_fields(client):
    h = _reg(client, "nb4@x.com")
    n = client.post("/api/notes", headers=h, json={
        "note_text": "Renew Passport", "is_favorite": True,
        "due_date": "2026-07-01", "due_time": "09:00", "repeat": "yearly"}).json()
    assert n["is_favorite"] and n["repeat"] == "yearly" and n["due_time"] == "09:00"
    # favorites filter
    favs = client.get("/api/notes?is_favorite=true", headers=h).json()
    assert any(x["id"] == n["id"] for x in favs)
    # reminders view = notes with a due date
    rem = client.get("/api/notes?has_reminder=true", headers=h).json()
    assert any(x["id"] == n["id"] for x in rem)


def test_move_note_between_notebooks(client):
    h = _reg(client, "nb5@x.com")
    a = client.post("/api/notebooks", headers=h, json={"name": "A"}).json()
    b = client.post("/api/notebooks", headers=h, json={"name": "B"}).json()
    n = client.post("/api/notes", headers=h, json={"note_text": "move me", "notebook_id": a["id"]}).json()
    r = client.put(f"/api/notes/{n['id']}", headers=h, json={"notebook_id": b["id"]})
    assert r.status_code == 200 and r.json()["notebook_id"] == b["id"]


def test_delete_notebook_rehomes_notes(client):
    h = _reg(client, "nb6@x.com")
    nb = client.post("/api/notebooks", headers=h, json={"name": "Temp"}).json()
    n = client.post("/api/notes", headers=h, json={"note_text": "keep me", "notebook_id": nb["id"]}).json()
    r = client.delete(f"/api/notebooks/{nb['id']}", headers=h)
    assert r.status_code == 200
    got = client.get(f"/api/notes/{n['id']}", headers=h).json()
    assert got["notebook_id"] is not None and got["notebook_id"] != nb["id"]   # moved, not deleted


def test_cannot_delete_default_notebook(client):
    h = _reg(client, "nb7@x.com")
    client.post("/api/notes", headers=h, json={"note_text": "x"})   # ensures default exists
    default = next(x for x in client.get("/api/notebooks", headers=h).json() if x["is_default"])
    r = client.delete(f"/api/notebooks/{default['id']}", headers=h)
    assert r.status_code == 400


def test_notebook_isolation_between_users(client):
    h1 = _reg(client, "nb8a@x.com")
    h2 = _reg(client, "nb8b@x.com")
    nb = client.post("/api/notebooks", headers=h1, json={"name": "Private"}).json()
    assert client.get(f"/api/notebooks/{nb['id']}", headers=h2).status_code == 404
    assert all(x["id"] != nb["id"] for x in client.get("/api/notebooks", headers=h2).json())
