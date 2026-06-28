from __future__ import annotations


def test_register_login_me(client):
    r = client.post("/api/auth/register", json={"email": "a@b.com", "password": "password123", "full_name": "A"})
    assert r.status_code == 201
    tokens = r.json()
    assert tokens["access_token"] and tokens["refresh_token"]
    assert tokens["user"]["email"] == "a@b.com"
    assert "password" not in r.text and "password_hash" not in r.text

    r = client.post("/api/auth/login", json={"email": "a@b.com", "password": "password123"})
    assert r.status_code == 200
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    me = client.get("/api/auth/me", headers=h)
    assert me.status_code == 200 and me.json()["email"] == "a@b.com"


def test_duplicate_email_rejected(client):
    client.post("/api/auth/register", json={"email": "d@b.com", "password": "password123"})
    r = client.post("/api/auth/register", json={"email": "d@b.com", "password": "password123"})
    assert r.status_code == 409


def test_bad_login_and_no_enumeration(client):
    client.post("/api/auth/register", json={"email": "x@b.com", "password": "password123"})
    assert client.post("/api/auth/login", json={"email": "x@b.com", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "nobody@b.com", "password": "x"}).status_code == 401


def test_unauthenticated_blocked(client):
    assert client.get("/api/reminders").status_code == 401
    assert client.get("/api/dashboard").status_code == 401


def test_refresh_and_change_and_reset_password(client):
    reg = client.post("/api/auth/register", json={"email": "c@b.com", "password": "password123"}).json()
    h = {"Authorization": f"Bearer {reg['access_token']}"}

    # refresh rotates
    r = client.post("/api/auth/refresh", json={"refresh_token": reg["refresh_token"]})
    assert r.status_code == 200 and r.json()["access_token"]

    # change password (wrong current → 400, correct → 200)
    assert client.post("/api/auth/change-password", headers=h,
                       json={"current_password": "nope", "new_password": "newpass1234"}).status_code == 400
    assert client.post("/api/auth/change-password", headers=h,
                       json={"current_password": "password123", "new_password": "newpass1234"}).status_code == 200
    assert client.post("/api/auth/login", json={"email": "c@b.com", "password": "newpass1234"}).status_code == 200

    # forgot → dev token → reset
    f = client.post("/api/auth/forgot-password", json={"email": "c@b.com"}).json()
    token = f.get("dev_token")
    assert token
    assert client.post("/api/auth/reset-password",
                       json={"token": token, "new_password": "resetpass99"}).status_code == 200
    assert client.post("/api/auth/login", json={"email": "c@b.com", "password": "resetpass99"}).status_code == 200
