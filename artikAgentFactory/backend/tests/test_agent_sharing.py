from tests.conftest import login_as


def test_private_agent_visible_only_to_owner_and_admin(client):
    login_as(client, "agent_manager")
    resp = client.post("/api/agents", json={"template_id": "general_research", "name": "Private", "objective": "o"})
    agent_id = resp.json()["id"]
    assert resp.json()["visibility"] == "private"
    client.post("/api/auth/logout")

    login_as(client, "researcher")
    assert client.get(f"/api/agents/{agent_id}").status_code == 404
    client.post("/api/auth/logout")

    login_as(client, "administrator")
    assert client.get(f"/api/agents/{agent_id}").status_code == 200


def test_toggling_visibility_to_shared_grants_workspace_baseline_immediately(client):
    login_as(client, "agent_manager")
    resp = client.post("/api/agents", json={"template_id": "general_research", "name": "Toggle", "objective": "o"})
    agent_id = resp.json()["id"]
    client.post("/api/auth/logout")

    login_as(client, "viewer")
    assert client.get(f"/api/agents/{agent_id}").status_code == 404
    client.post("/api/auth/logout")

    login_as(client, "agent_manager")
    resp = client.put(f"/api/agents/{agent_id}", json={"visibility": "shared"})
    assert resp.status_code == 200
    client.post("/api/auth/logout")

    login_as(client, "viewer")
    assert client.get(f"/api/agents/{agent_id}").status_code == 200


def test_revoking_toggling_back_to_private_removes_workspace_baseline(client):
    login_as(client, "agent_manager")
    resp = client.post("/api/agents", json={
        "template_id": "general_research", "name": "Toggle Back", "objective": "o", "visibility": "shared",
    })
    agent_id = resp.json()["id"]
    client.post("/api/auth/logout")

    login_as(client, "viewer")
    assert client.get(f"/api/agents/{agent_id}").status_code == 200
    client.post("/api/auth/logout")

    login_as(client, "agent_manager")
    client.put(f"/api/agents/{agent_id}", json={"visibility": "private"})
    client.post("/api/auth/logout")

    login_as(client, "viewer")
    assert client.get(f"/api/agents/{agent_id}").status_code == 404


def test_explicit_grant_survives_agent_being_private(client):
    login_as(client, "administrator")
    resp = client.post("/api/users", json={
        "email": "survivor@test.local", "username": "survivor", "password": "orbit-battery-pass-9", "role": "viewer",
    })
    uid = resp.json()["id"]
    client.post("/api/auth/logout")

    login_as(client, "agent_manager")
    resp = client.post("/api/agents", json={"template_id": "general_research", "name": "Grant Survives", "objective": "o"})
    agent_id = resp.json()["id"]
    resp = client.post(f"/api/agents/{agent_id}/access", json={"user_id": uid, "access_level": "viewer"})
    assert resp.status_code == 201, resp.text
    client.post("/api/auth/logout")

    client.post("/api/auth/login", json={"identifier": "survivor@test.local", "password": "orbit-battery-pass-9"})
    client.post("/api/auth/change-password", json={"current_password": "orbit-battery-pass-9", "new_password": "orbit-new-battery-9"})
    resp = client.get(f"/api/agents/{agent_id}")
    assert resp.status_code == 200  # explicit grant works even though agent stays private
