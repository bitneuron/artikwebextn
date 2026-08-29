"""Agent CRUD + lifecycle. Run execution itself lives in services.run_service (Phase C)
so this file stays about configuration, not research."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.utils import from_json, to_json
from app.models.agent import Agent
from app.models.alert import AlertRule
from app.repositories.agent_repo import AgentRepository
from app.templates.registry import get_template


class AgentNotFound(Exception):
    pass


class UnknownTemplate(Exception):
    pass


class AgentService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = AgentRepository(db)

    # ── serialization ─────────────────────────────────────────────────────────
    def to_out(self, a: Agent) -> dict:
        return {
            "id": a.id, "template_id": a.template_id, "name": a.name,
            "owner_id": a.owner_id, "workspace_id": a.workspace_id, "visibility": a.visibility,
            "description": a.description, "objective": a.objective, "status": a.status,
            "tags": from_json(a.tags, []), "result_language": a.result_language,
            "time_zone": a.time_zone, "filters": from_json(a.filters_json, {}),
            "profile": from_json(a.profile_json, None) if a.profile_json else None,
            "schedule": from_json(a.schedule_json, {"mode": "manual"}),
            "is_schedule_enabled": a.is_schedule_enabled,
            "last_run_id": a.last_run_id, "last_run_at": a.last_run_at,
            "last_run_status": a.last_run_status, "next_run_at": a.next_run_at,
            "alert_rules": [self._rule_out(r) for r in a.alert_rules],
            "created_at": a.created_at, "updated_at": a.updated_at,
        }

    def to_list_item(self, a: Agent, *, can_manage: bool = True, can_run: bool = True) -> dict:
        total = len(a.results)
        new = sum(1 for r in a.results if r.change_status == "new" and not r.is_dismissed)
        changed = sum(1 for r in a.results if r.change_status == "changed" and not r.is_dismissed)
        high_priority = sum(1 for r in a.results if r.priority_flag and not r.is_dismissed)
        return {
            "id": a.id, "template_id": a.template_id, "name": a.name,
            "owner_id": a.owner_id, "visibility": a.visibility,
            "description": a.description, "status": a.status, "tags": from_json(a.tags, []),
            "is_schedule_enabled": a.is_schedule_enabled, "last_run_at": a.last_run_at,
            "last_run_status": a.last_run_status, "next_run_at": a.next_run_at,
            "result_count_total": total, "result_count_new": new,
            "result_count_changed": changed, "high_priority_count": high_priority,
            "can_manage": can_manage, "can_run": can_run,
            "created_at": a.created_at, "updated_at": a.updated_at,
        }

    def _rule_out(self, r: AlertRule) -> dict:
        return {
            "id": r.id, "agent_id": r.agent_id, "rule_type": r.rule_type,
            "channel": r.channel, "is_enabled": r.is_enabled,
            "config": from_json(r.config_json, {}), "created_at": r.created_at,
        }

    # ── CRUD ──────────────────────────────────────────────────────────────────
    def create(self, data, *, owner_id: int, workspace_id: int) -> Agent:
        template = get_template(data.template_id)
        if not template:
            raise UnknownTemplate(data.template_id)
        a = Agent(
            template_id=data.template_id, owner_id=owner_id, workspace_id=workspace_id,
            visibility=getattr(data, "visibility", None) or "private",
            name=data.name, description=data.description,
            objective=data.objective, tags=to_json(data.tags),
            result_language=data.result_language, time_zone=data.time_zone,
            filters_json=to_json(data.filters),
            profile_json=to_json(data.profile) if data.profile is not None else None,
            schedule_json=to_json(data.schedule), is_schedule_enabled=data.is_schedule_enabled,
            status=data.status,
        )
        self.repo.add(a)
        self._apply_alert_rules(a, data.alert_rules or [_default_rule(d) for d in template.default_alert_rules])
        self.db.commit()
        self.db.refresh(a)
        return a

    def get(self, agent_id: int) -> Agent:
        a = self.repo.get(agent_id)
        if not a or a.status == "archived":
            raise AgentNotFound()
        return a

    def get_any(self, agent_id: int) -> Agent:
        a = self.repo.get(agent_id)
        if not a:
            raise AgentNotFound()
        return a

    def list(self, **kw) -> list[Agent]:
        return self.repo.query(**kw)

    def update(self, agent_id: int, data) -> Agent:
        a = self.get(agent_id)
        fields = data.model_dump(exclude_unset=True)
        for f in ("name", "description", "objective", "result_language", "time_zone", "status", "visibility"):
            if f in fields and fields[f] is not None:
                setattr(a, f, fields[f])
        if "tags" in fields and fields["tags"] is not None:
            a.tags = to_json(fields["tags"])
        if "filters" in fields and fields["filters"] is not None:
            a.filters_json = to_json(fields["filters"])
        if "profile" in fields:
            a.profile_json = to_json(fields["profile"]) if fields["profile"] is not None else None
        if "schedule" in fields and fields["schedule"] is not None:
            a.schedule_json = to_json(fields["schedule"])
        if "is_schedule_enabled" in fields and fields["is_schedule_enabled"] is not None:
            a.is_schedule_enabled = fields["is_schedule_enabled"]
        if "alert_rules" in fields and fields["alert_rules"] is not None:
            self._apply_alert_rules(a, data.alert_rules)
        self.db.commit()
        self.db.refresh(a)
        return a

    def _apply_alert_rules(self, a: Agent, rules) -> None:
        for r in list(a.alert_rules):
            self.db.delete(r)
        self.db.flush()
        for r in rules:
            self.db.add(AlertRule(
                agent_id=a.id, rule_type=r.rule_type if hasattr(r, "rule_type") else r["rule_type"],
                channel=(r.channel if hasattr(r, "channel") else r.get("channel", "in_app")),
                config_json=to_json(r.config if hasattr(r, "config") else r.get("config", {})),
                is_enabled=(r.is_enabled if hasattr(r, "is_enabled") else r.get("is_enabled", True)),
            ))

    def pause(self, agent_id: int) -> Agent:
        a = self.get(agent_id)
        a.status = "paused"
        self.db.commit()
        self.db.refresh(a)
        return a

    def resume(self, agent_id: int) -> Agent:
        a = self.get(agent_id)
        a.status = "active"
        self.db.commit()
        self.db.refresh(a)
        return a

    def archive(self, agent_id: int) -> None:
        a = self.get(agent_id)
        a.status = "archived"
        a.is_schedule_enabled = False
        self.db.commit()

    def duplicate(self, agent_id: int, *, owner_id: int, workspace_id: int) -> Agent:
        a = self.get(agent_id)
        copy = Agent(
            template_id=a.template_id, owner_id=owner_id, workspace_id=workspace_id, visibility="private",
            name=f"{a.name} (copy)", description=a.description,
            objective=a.objective, tags=a.tags, result_language=a.result_language,
            time_zone=a.time_zone, filters_json=a.filters_json, profile_json=a.profile_json,
            schedule_json=a.schedule_json, is_schedule_enabled=False, status="paused",
        )
        self.repo.add(copy)
        for r in a.alert_rules:
            self.db.add(AlertRule(agent_id=copy.id, rule_type=r.rule_type, channel=r.channel,
                                  config_json=r.config_json, is_enabled=r.is_enabled))
        self.db.commit()
        self.db.refresh(copy)
        return copy


def _default_rule(d: dict):
    from app.schemas.agent import AlertRuleIn
    return AlertRuleIn(rule_type=d["rule_type"], channel=d.get("channel", "in_app"), config=d.get("config", {}))
