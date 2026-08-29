from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, login_as


def _actions(client, **params):
    resp = client.get("/api/audit-events", params=params)
    assert resp.status_code == 200
    return [e["action"] for e in resp.json()]


def test_login_success_and_failure_are_audited(client):
    client.post("/api/auth/login", json={"identifier": ADMIN_EMAIL, "password": "wrong"})
    client.post("/api/auth/login", json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    login_as(client, "administrator")  # already logged in above; re-login is harmless

    actions = _actions(client)
    assert "auth.login_success" in actions
    assert "auth.login_failure" in actions


def test_agent_crud_is_audited(client):
    login_as(client, "administrator")
    resp = client.post("/api/agents", json={"template_id": "general_research", "name": "Audited", "objective": "o"})
    agent_id = resp.json()["id"]
    client.put(f"/api/agents/{agent_id}", json={"name": "Renamed"})
    client.delete(f"/api/agents/{agent_id}")

    actions = _actions(client)
    assert "agent.create" in actions
    assert "agent.update" in actions
    assert "agent.delete" in actions


def test_denied_access_is_audited(client):
    login_as(client, "viewer")
    client.post("/api/agents", json={"template_id": "general_research", "name": "x", "objective": "o"})  # denied
    client.post("/api/auth/logout")

    login_as(client, "administrator")
    actions = _actions(client, outcome="denied")
    assert "access.denied" in actions


def test_audit_metadata_never_contains_secret_shaped_keys(client):
    from app.auth.audit import record_audit
    from app.core.database import SessionLocal
    import json as jsonlib

    db = SessionLocal()
    try:
        record_audit(db, actor=None, action="test.action", resource_type="test",
                     outcome="success", metadata={"password": "shouldnotpersist", "safe_field": "ok", "api_key": "shh"})
        db.commit()
        from app.models.audit_event import AuditEvent
        row = db.query(AuditEvent).filter(AuditEvent.action == "test.action").first()
        meta = jsonlib.loads(row.metadata_json)
        assert "password" not in meta
        assert "api_key" not in meta
        assert meta.get("safe_field") == "ok"
    finally:
        db.close()


def test_viewing_audit_log_is_itself_audited(client):
    login_as(client, "administrator")
    client.get("/api/audit-events")
    actions = _actions(client)
    assert "audit.view" in actions
