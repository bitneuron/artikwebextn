from app.services.pipeline.log_scrub import _scrub, log_run
from app.models.run_log import RunLog


def test_scrubs_anthropic_style_key():
    out = _scrub("failed with key sk-ant-api03-XyZ1234567890abcdefGHIJKLMNOP")
    assert "sk-ant" not in out
    assert "[redacted]" in out


def test_scrubs_bearer_token():
    out = _scrub("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig")
    assert "eyJ" not in out
    assert "[redacted]" in out


def test_scrubs_quoted_dict_style_api_key():
    out = _scrub("headers={'X-API-Key': 'super-secret-value-here'}")
    assert "super-secret-value-here" not in out


def test_leaves_normal_messages_untouched():
    msg = "5 unique result(s) after dedup (2 duplicate(s) dropped)"
    assert _scrub(msg) == msg


def test_log_run_persists_scrubbed_message(db_session):
    from app.models.agent import Agent
    from app.models.run import AgentRun
    from app.models.user import User
    from app.models.workspace import Workspace

    ws = Workspace(name="Test", slug="test-ws-logscrub")
    db_session.add(ws)
    db_session.flush()
    owner = User(email="logscrub@test.local", username="logscrub", password_hash="x",
                role="administrator", workspace_id=ws.id)
    db_session.add(owner)
    db_session.flush()
    agent = Agent(template_id="general_research", name="t", objective="o",
                  owner_id=owner.id, workspace_id=ws.id)
    db_session.add(agent)
    db_session.flush()
    run = AgentRun(agent_id=agent.id, trigger="manual", status="running")
    db_session.add(run)
    db_session.flush()

    log_run(db_session, run.id, "web_search", "key=sk-ant-api03-abcdefghijklmnop", level="error")
    db_session.commit()

    row = db_session.query(RunLog).filter(RunLog.run_id == run.id).one()
    assert "sk-ant" not in row.message
    assert row.level == "error"
    assert row.stage == "web_search"
