from tests.conftest import login_as


def _email_draft(**filters):
    return {
        "template_id": "email_scheduler",
        "name": "Weekly reminder",
        "objective": "Send myself a weekly reminder email",
        "filters": {"to_email": "recipient@example.com", "subject": "Reminder", "message": "Hi!", **filters},
        "schedule": {"mode": "manual"},
    }


def test_run_now_fails_cleanly_when_gmail_not_configured(client, monkeypatch):
    monkeypatch.delenv("GMAIL_SMTP_USER", raising=False)
    monkeypatch.delenv("GMAIL_SMTP_APP_PASSWORD", raising=False)
    login_as(client, "administrator")
    resp = client.post("/api/agents", json=_email_draft())
    agent_id = resp.json()["id"]

    resp = client.post(f"/api/agents/{agent_id}/run")
    assert resp.status_code == 200
    run = resp.json()
    assert run["status"] == "failed"
    assert "not configured" in run["error_message"]
    assert run["result_count_total"] == 0


def test_run_now_sends_email_when_gmail_configured(client, monkeypatch):
    monkeypatch.setenv("GMAIL_SMTP_USER", "me@example.com")
    monkeypatch.setenv("GMAIL_SMTP_APP_PASSWORD", "app-password")
    monkeypatch.setattr("app.services.run_service.send_email", lambda **kw: (True, "sent"))
    login_as(client, "administrator")
    resp = client.post("/api/agents", json=_email_draft())
    agent_id = resp.json()["id"]

    resp = client.post(f"/api/agents/{agent_id}/run")
    assert resp.status_code == 200
    run = resp.json()
    assert run["status"] == "completed"


def test_run_now_rejected_without_recipient(client, monkeypatch):
    monkeypatch.setenv("GMAIL_SMTP_USER", "me@example.com")
    monkeypatch.setenv("GMAIL_SMTP_APP_PASSWORD", "app-password")
    login_as(client, "administrator")
    resp = client.post("/api/agents", json=_email_draft(to_email=""))
    agent_id = resp.json()["id"]

    resp = client.post(f"/api/agents/{agent_id}/run")
    assert resp.status_code == 200
    run = resp.json()
    assert run["status"] == "failed"
    assert "recipient" in run["error_message"]
