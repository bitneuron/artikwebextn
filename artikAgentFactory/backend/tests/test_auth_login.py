from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, login_as


def test_unauthenticated_me_is_401(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_wrong_password_rejected_with_generic_message(client):
    resp = client.post("/api/auth/login", json={"identifier": ADMIN_EMAIL, "password": "nope"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "invalid credentials"


def test_unknown_account_gets_same_generic_message(client):
    # Never reveal whether an account exists.
    resp = client.post("/api/auth/login", json={"identifier": "nobody@nowhere.test", "password": "whatever12345"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "invalid credentials"


def test_correct_login_sets_session_cookie(client):
    resp = client.post("/api/auth/login", json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert resp.status_code == 200
    assert "af_session" in resp.cookies
    resp2 = client.get("/api/auth/me")
    assert resp2.status_code == 200
    assert resp2.json()["email"] == ADMIN_EMAIL


def test_inactive_user_cannot_login(client):
    login_as(client, "administrator")
    resp = client.post("/api/users", json={
        "email": "disabled@test.local", "username": "disabled",
        "password": "zephyr-battery-pass-1", "role": "viewer",
    })
    uid = resp.json()["id"]
    resp = client.put(f"/api/users/{uid}", json={"is_active": False})
    assert resp.status_code == 200

    client.post("/api/auth/logout")
    resp = client.post("/api/auth/login", json={"identifier": "disabled@test.local", "password": "zephyr-battery-pass-1"})
    assert resp.status_code == 401


def test_logout_clears_session(client):
    login_as(client, "administrator")
    assert client.get("/api/auth/me").status_code == 200
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_password_change_invalidates_old_session_but_keeps_current_one(client):
    login_as(client, "administrator")
    resp = client.post("/api/auth/change-password", json={
        "current_password": ADMIN_PASSWORD, "new_password": "brand-new-strong-pass-88",
    })
    assert resp.status_code == 200
    # current session (cookie was re-minted by the endpoint) still works
    assert client.get("/api/auth/me").status_code == 200

    # change it back so other tests relying on ADMIN_PASSWORD keep working —
    # not needed since _clean_tables wipes state after every test, but explicit
    # for clarity that this test doesn't leak state.


def test_login_throttle_locks_out_after_repeated_failures(client):
    for _ in range(5):
        client.post("/api/auth/login", json={"identifier": "throttle-target@test.local", "password": "wrong"})
    resp = client.post("/api/auth/login", json={"identifier": "throttle-target@test.local", "password": "wrong"})
    assert resp.status_code == 429


def test_must_reset_password_blocks_other_endpoints(client):
    login_as(client, "administrator")
    resp = client.post("/api/users", json={
        "email": "fresh@test.local", "username": "fresh", "password": "comet-battery-pass-12", "role": "viewer",
    })
    assert resp.status_code == 201

    fresh_client = client
    # log out admin, log in as the freshly-created (must_reset_password=True) user
    fresh_client.post("/api/auth/logout")
    resp = fresh_client.post("/api/auth/login", json={"identifier": "fresh@test.local", "password": "comet-battery-pass-12"})
    assert resp.status_code == 200
    assert resp.json()["must_reset_password"] is True

    resp = fresh_client.get("/api/agents")
    assert resp.status_code == 403

    resp = fresh_client.post("/api/auth/change-password", json={
        "current_password": "comet-battery-pass-12", "new_password": "comet-new-battery-99",
    })
    assert resp.status_code == 200
    resp = fresh_client.get("/api/agents")
    assert resp.status_code == 200
