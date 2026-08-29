from tests.conftest import login_as


def test_user_management_is_admin_only(client):
    for role in ("agent_manager", "researcher", "viewer"):
        login_as(client, role)
        resp = client.get("/api/users")
        assert resp.status_code == 403, role
        resp = client.post("/api/users", json={
            "email": f"x-{role}@test.local", "username": f"x{role}",
            "password": "whatever-strong-pass-9", "role": "viewer",
        })
        assert resp.status_code == 403, role
        client.post("/api/auth/logout")

    login_as(client, "administrator")
    assert client.get("/api/users").status_code == 200


def test_audit_log_is_admin_only(client):
    for role in ("agent_manager", "researcher", "viewer"):
        login_as(client, role)
        resp = client.get("/api/audit-events")
        assert resp.status_code == 403, role
        client.post("/api/auth/logout")

    login_as(client, "administrator")
    assert client.get("/api/audit-events").status_code == 200


def test_notification_settings_are_admin_only(client):
    for role in ("agent_manager", "researcher", "viewer"):
        login_as(client, role)
        assert client.get("/api/notification-settings").status_code == 403, role
        assert client.put("/api/notification-settings", json={"slack_enabled": False}).status_code == 403, role
        client.post("/api/auth/logout")

    login_as(client, "administrator")
    assert client.get("/api/notification-settings").status_code == 200
