"""The core IDOR-prevention regression test: every role × every relationship to an
agent (owner / explicit grant / unrelated-private / workspace-shared) must resolve to
exactly the status code the approved plan's access model predicts."""
import pytest

from tests.conftest import login_as


def _create_agent(client, **overrides):
    body = {"template_id": "general_research", "name": "Matrix Agent", "objective": "o",
           "filters": {}, "schedule": {"mode": "manual"}}
    body.update(overrides)
    resp = client.post("/api/agents", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_only_administrator_and_agent_manager_can_create_agents(client):
    for role, expected in [("administrator", 201), ("agent_manager", 201), ("researcher", 403), ("viewer", 403)]:
        login_as(client, role)
        resp = client.post("/api/agents", json={
            "template_id": "general_research", "name": f"by-{role}", "objective": "o",
        })
        assert resp.status_code == expected, (role, resp.status_code, resp.text)
        client.post("/api/auth/logout")


def test_unrelated_private_agent_is_404_for_everyone_but_admin(client):
    login_as(client, "agent_manager")
    agent_id = _create_agent(client)
    client.post("/api/auth/logout")

    for role in ("researcher", "viewer"):
        login_as(client, role)
        resp = client.get(f"/api/agents/{agent_id}")
        assert resp.status_code == 404, (role, resp.status_code)
        client.post("/api/auth/logout")

    login_as(client, "administrator")
    resp = client.get(f"/api/agents/{agent_id}")
    assert resp.status_code == 200  # admin bypass


def test_shared_agent_grants_workspace_wide_viewer_baseline(client):
    login_as(client, "administrator")
    agent_id = _create_agent(client, visibility="shared")
    client.post("/api/auth/logout")

    login_as(client, "viewer")
    resp = client.get(f"/api/agents/{agent_id}")
    assert resp.status_code == 200
    resp = client.put(f"/api/agents/{agent_id}", json={"name": "hack"})
    assert resp.status_code == 403
    resp = client.post(f"/api/agents/{agent_id}/run")
    assert resp.status_code == 403


@pytest.mark.parametrize("grant_level,can_edit,can_run", [
    ("viewer", False, False),
    ("researcher", False, True),
    ("manager", True, True),
])
def test_explicit_grant_levels_match_expected_capabilities(client, grant_level, can_edit, can_run, monkeypatch):
    monkeypatch.setattr("app.services.pipeline.searcher.get_anthropic_api_key", lambda: "")

    login_as(client, "administrator")
    agent_id = _create_agent(client)
    resp = client.post("/api/users", json={
        "email": f"grantee-{grant_level}@test.local", "username": f"grantee{grant_level}",
        "password": "grantee-strong-pass-99", "role": "viewer",
    })
    user_id = resp.json()["id"]
    resp = client.post(f"/api/agents/{agent_id}/access", json={"user_id": user_id, "access_level": grant_level})
    assert resp.status_code == 201
    client.post("/api/auth/logout")

    resp = client.post("/api/auth/login", json={"identifier": f"grantee-{grant_level}@test.local", "password": "grantee-strong-pass-99"})
    assert resp.status_code == 200
    client.post("/api/auth/change-password", json={
        "current_password": "grantee-strong-pass-99", "new_password": "grantee-new-strong-pass-99",
    })

    resp = client.get(f"/api/agents/{agent_id}")
    assert resp.status_code == 200  # any grant level implies at least viewer

    resp = client.put(f"/api/agents/{agent_id}", json={"name": "renamed"})
    assert (resp.status_code == 200) == can_edit, (grant_level, "edit", resp.status_code)

    resp = client.post(f"/api/agents/{agent_id}/run")
    assert (resp.status_code == 200) == can_run, (grant_level, "run", resp.status_code)


def test_non_owner_manager_grant_cannot_reshare(client):
    login_as(client, "administrator")
    agent_id = _create_agent(client)
    resp = client.post("/api/users", json={
        "email": "manager-grantee@test.local", "username": "managergrantee",
        "password": "nimbus-battery-pass-99", "role": "researcher",
    })
    grantee_id = resp.json()["id"]
    client.post(f"/api/agents/{agent_id}/access", json={"user_id": grantee_id, "access_level": "manager"})

    resp = client.post("/api/users", json={
        "email": "third-party@test.local", "username": "thirdparty",
        "password": "lumen-battery-pass-99", "role": "viewer",
    })
    third_party_id = resp.json()["id"]
    client.post("/api/auth/logout")

    client.post("/api/auth/login", json={"identifier": "manager-grantee@test.local", "password": "nimbus-battery-pass-99"})
    client.post("/api/auth/change-password", json={"current_password": "nimbus-battery-pass-99", "new_password": "nimbus-new-battery-99"})

    resp = client.post(f"/api/agents/{agent_id}/access", json={"user_id": third_party_id, "access_level": "viewer"})
    assert resp.status_code == 403  # a manager-level GRANT (not ownership) cannot re-share


def test_admin_can_delete_agent_it_does_not_own(client):
    login_as(client, "agent_manager")
    agent_id = _create_agent(client)
    client.post("/api/auth/logout")

    login_as(client, "administrator")
    resp = client.delete(f"/api/agents/{agent_id}")
    assert resp.status_code == 200


def test_deleted_agent_returns_404_not_leaked_via_results(client):
    login_as(client, "administrator")
    agent_id = _create_agent(client)
    client.delete(f"/api/agents/{agent_id}")

    resp = client.get(f"/api/agents/{agent_id}")
    assert resp.status_code == 404
    resp = client.get(f"/api/agents/{agent_id}/results")
    assert resp.status_code == 404
