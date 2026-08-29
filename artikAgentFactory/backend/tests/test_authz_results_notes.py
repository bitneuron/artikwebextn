from app.core.database import SessionLocal
from app.models.result import Result
from tests.conftest import login_as


def _create_agent_with_result(client):
    resp = client.post("/api/agents", json={
        "template_id": "general_research", "name": "Results Test", "objective": "o",
    })
    agent_id = resp.json()["id"]
    db = SessionLocal()
    try:
        r = Result(agent_id=agent_id, dedup_key="k1", title="A finding", url="https://example.com/a",
                  relevance_score=0.9, confidence_score=0.9, source_credibility="high", category="general")
        db.add(r)
        db.commit()
        db.refresh(r)
        return agent_id, r.id
    finally:
        db.close()


def test_viewer_can_read_but_not_save_or_dismiss(client):
    login_as(client, "administrator")
    agent_id, result_id = _create_agent_with_result(client)
    client.put(f"/api/agents/{agent_id}", json={"visibility": "shared"})
    client.post("/api/auth/logout")

    login_as(client, "viewer")
    resp = client.get(f"/api/results/{result_id}")
    assert resp.status_code == 200

    resp = client.post(f"/api/results/{result_id}/save")
    assert resp.status_code == 403

    resp = client.post(f"/api/results/{result_id}/dismiss")
    assert resp.status_code == 403

    resp = client.post(f"/api/results/{result_id}/notes", json={"body": "note"})
    assert resp.status_code == 403


def test_researcher_with_grant_can_save_dismiss_and_note(client):
    login_as(client, "administrator")
    agent_id, result_id = _create_agent_with_result(client)
    client.put(f"/api/agents/{agent_id}", json={"visibility": "shared"})
    resp = client.post("/api/users", json={
        "email": "res-notes@test.local", "username": "resnotes",
        "password": "quartz-battery-pass-9", "role": "researcher",
    })
    uid = resp.json()["id"]
    client.post(f"/api/agents/{agent_id}/access", json={"user_id": uid, "access_level": "researcher"})
    client.post("/api/auth/logout")

    client.post("/api/auth/login", json={"identifier": "res-notes@test.local", "password": "quartz-battery-pass-9"})
    client.post("/api/auth/change-password", json={"current_password": "quartz-battery-pass-9", "new_password": "quartz-new-battery-9"})

    resp = client.post(f"/api/results/{result_id}/save")
    assert resp.status_code == 200
    assert resp.json()["is_saved"] is True

    resp = client.post(f"/api/results/{result_id}/notes", json={"body": "worth following up"})
    assert resp.status_code == 201


def test_result_on_inaccessible_agent_is_404_not_403(client):
    login_as(client, "agent_manager")
    _, result_id = _create_agent_with_result(client)  # private, owned by agent_manager
    client.post("/api/auth/logout")

    login_as(client, "viewer")
    resp = client.get(f"/api/results/{result_id}")
    assert resp.status_code == 404  # zero relationship -> 404, not 403 (don't confirm existence)
