from datetime import datetime, timezone

from app.models.agent import Agent
from app.models.alert import AlertRule
from app.models.run import AgentRun
from app.models.user import User
from app.models.workspace import Workspace
from app.services.pipeline.alerts import deliver_alert_events, run_alert_rules
from app.templates.registry import get_template


def _make_agent(db, *, channel="slack"):
    ws = Workspace(name="Idem", slug="idem-ws")
    db.add(ws)
    db.flush()
    owner = User(email="idem@test.local", username="idem", password_hash="x",
                role="administrator", workspace_id=ws.id)
    db.add(owner)
    db.flush()
    agent = Agent(template_id="general_research", name="Idempotency Test", objective="o",
                 owner_id=owner.id, workspace_id=ws.id)
    db.add(agent)
    db.flush()
    rule = AlertRule(agent_id=agent.id, rule_type="run_completed", channel=channel, is_enabled=True)
    db.add(rule)
    db.flush()
    db.refresh(agent)
    return agent


def test_deliver_alert_events_sends_exactly_once_per_run(db_session, monkeypatch):
    call_count = {"n": 0}

    def fake_send(*, event_type, severity, title, message, metadata=None):
        call_count["n"] += 1
        return True, "sent"

    monkeypatch.setattr("app.services.pipeline.alerts.slack_configured", lambda: True)
    monkeypatch.setattr("app.services.pipeline.alerts.send_slack_notification", fake_send)

    agent = _make_agent(db_session)
    run = AgentRun(agent_id=agent.id, trigger="manual", status="completed",
                   started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc),
                   duration_seconds=1.0, result_count_new=1, result_count_total=1)
    db_session.add(run)
    db_session.flush()

    events = run_alert_rules(db_session, agent, run, [])
    db_session.commit()
    template = get_template(agent.template_id)

    deliver_alert_events(db_session, agent, template, run, [], events)
    assert call_count["n"] == 1

    # Calling delivery again for the SAME run/events must not send a second time —
    # this is the idempotency guarantee the (agent_id, run_id, notification_type)
    # unique constraint backs.
    deliver_alert_events(db_session, agent, template, run, [], events)
    assert call_count["n"] == 1

    from app.models.notification_delivery import NotificationDelivery
    rows = db_session.query(NotificationDelivery).filter_by(agent_id=agent.id, run_id=run.id).all()
    assert len(rows) == 1
    assert rows[0].status == "sent"
    assert rows[0].idempotency_key == f"{agent.id}:{run.id}:run_completed"


def test_in_app_channel_never_calls_slack(db_session, monkeypatch):
    call_count = {"n": 0}
    monkeypatch.setattr("app.services.pipeline.alerts.slack_configured", lambda: True)
    monkeypatch.setattr("app.services.pipeline.alerts.send_slack_notification",
                        lambda **kw: call_count.__setitem__("n", call_count["n"] + 1) or (True, "sent"))

    agent = _make_agent(db_session, channel="in_app")
    run = AgentRun(agent_id=agent.id, trigger="manual", status="completed",
                   started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc),
                   duration_seconds=1.0, result_count_total=0)
    db_session.add(run)
    db_session.flush()

    events = run_alert_rules(db_session, agent, run, [])
    db_session.commit()
    deliver_alert_events(db_session, agent, get_template(agent.template_id), run, [], events)
    assert call_count["n"] == 0


def test_disabled_workspace_setting_skips_delivery(db_session, monkeypatch):
    from app.models.notification_settings import NotificationSettings

    call_count = {"n": 0}
    monkeypatch.setattr("app.services.pipeline.alerts.slack_configured", lambda: True)
    monkeypatch.setattr("app.services.pipeline.alerts.send_slack_notification",
                        lambda **kw: call_count.__setitem__("n", call_count["n"] + 1) or (True, "sent"))

    agent = _make_agent(db_session)
    db_session.add(NotificationSettings(workspace_id=agent.workspace_id, slack_enabled=False))
    db_session.commit()

    run = AgentRun(agent_id=agent.id, trigger="manual", status="completed",
                   started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc),
                   duration_seconds=1.0, result_count_total=0)
    db_session.add(run)
    db_session.flush()
    events = run_alert_rules(db_session, agent, run, [])
    db_session.commit()

    deliver_alert_events(db_session, agent, get_template(agent.template_id), run, [], events)
    assert call_count["n"] == 0
