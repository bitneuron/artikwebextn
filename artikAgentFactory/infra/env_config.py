"""One place that describes what differs between staging and production. Everything
else in the stacks is identical code, parameterized by this config — no copy-pasted
stacks per environment."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EnvConfig:
    env_name: str                      # "staging" | "production"
    account: str
    region: str = "us-west-2"
    domain_name: str | None = None     # None = no Route53/ACM/CloudFront custom domain yet
    db_instance_class: str = "db.t4g.micro"
    db_multi_az: bool = False
    web_min_tasks: int = 1
    web_max_tasks: int = 2
    worker_min_tasks: int = 1
    worker_max_tasks: int = 2
    enable_waf: bool = True
    enable_cloudfront: bool = True
    log_retention_days: int = 30
    # A direct Slack Incoming Webhook to this app's own dedicated channel — see
    # backend/app/services/notify_client.py. Display-only; the real routing comes
    # from SLACK_WEBHOOK_URL (provisioned in data_stack.py, populated manually).
    slack_channel: str = "#artik-agent-notify"
    tags: dict = field(default_factory=dict)

    @property
    def resource_prefix(self) -> str:
        return f"artikagentfactory-{self.env_name}"


def staging(account: str) -> EnvConfig:
    return EnvConfig(
        env_name="staging", account=account,
        db_instance_class="db.t4g.micro", db_multi_az=False,
        web_min_tasks=1, web_max_tasks=1, worker_min_tasks=1, worker_max_tasks=1,
        enable_waf=True, enable_cloudfront=False,  # no custom domain yet -> skip edge stack pieces that need one
        log_retention_days=14,
        tags={"Project": "artikAgentFactory", "Environment": "staging"},
    )


def production(account: str) -> EnvConfig:
    return EnvConfig(
        env_name="production", account=account,
        db_instance_class="db.t4g.small", db_multi_az=True,
        web_min_tasks=2, web_max_tasks=6, worker_min_tasks=1, worker_max_tasks=3,
        enable_waf=True, enable_cloudfront=True,
        log_retention_days=90,
        tags={"Project": "artikAgentFactory", "Environment": "production"},
    )
