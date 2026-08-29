from tests.conftest import login_as


def _draft(template_id="general_research", **overrides):
    body = {
        "template_id": template_id,
        "name": "Test Agent",
        "objective": "Test objective",
        "filters": {},
        "schedule": {"mode": "manual"},
    }
    body.update(overrides)
    return body


def test_list_templates_returns_all_fifteen(client):
    login_as(client, "administrator")
    resp = client.get("/api/templates")
    assert resp.status_code == 200
    assert len(resp.json()) == 15


def test_create_agent_applies_template_default_alert_rules(client):
    login_as(client, "administrator")
    resp = client.post("/api/agents", json=_draft("scholarship_finder"))
    assert resp.status_code == 201
    agent = resp.json()
    assert agent["template_id"] == "scholarship_finder"
    assert len(agent["alert_rules"]) == 3  # new_results, deadline_approaching, run_error
    assert agent["status"] == "active"


def test_create_agent_unknown_template_rejected(client):
    login_as(client, "administrator")
    resp = client.post("/api/agents", json=_draft("not_a_real_template"))
    assert resp.status_code == 400


def test_full_agent_lifecycle(client):
    login_as(client, "administrator")
    resp = client.post("/api/agents", json=_draft())
    agent_id = resp.json()["id"]

    resp = client.get(f"/api/agents/{agent_id}")
    assert resp.status_code == 200

    resp = client.put(f"/api/agents/{agent_id}", json={"name": "Renamed"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed"

    resp = client.post(f"/api/agents/{agent_id}/pause")
    assert resp.json()["status"] == "paused"

    resp = client.post(f"/api/agents/{agent_id}/resume")
    assert resp.json()["status"] == "active"

    resp = client.post(f"/api/agents/{agent_id}/duplicate")
    assert resp.status_code == 201
    dup = resp.json()
    assert dup["id"] != agent_id
    assert dup["name"].endswith("(copy)")
    assert dup["status"] == "paused"

    resp = client.delete(f"/api/agents/{agent_id}")
    assert resp.status_code == 200
    resp = client.get(f"/api/agents/{agent_id}")
    assert resp.status_code == 404  # archived agents are excluded from GET-by-id (soft delete)


def test_list_agents_excludes_archived_by_default(client):
    login_as(client, "administrator")
    resp = client.post("/api/agents", json=_draft())
    agent_id = resp.json()["id"]
    client.delete(f"/api/agents/{agent_id}")

    resp = client.get("/api/agents")
    assert all(a["id"] != agent_id for a in resp.json())


def test_run_now_returns_a_run_even_with_no_api_key(client, monkeypatch):
    # Without ANTHROPIC_API_KEY configured, the pipeline should fail cleanly (not crash
    # the request) and record a failed run with a run_error alert.
    monkeypatch.setattr("app.services.pipeline.searcher.get_anthropic_api_key", lambda: "")
    login_as(client, "administrator")
    resp = client.post("/api/agents", json=_draft())
    agent_id = resp.json()["id"]

    resp = client.post(f"/api/agents/{agent_id}/run")
    assert resp.status_code == 200
    run = resp.json()
    assert run["status"] == "failed"
    assert run["error_message"]
