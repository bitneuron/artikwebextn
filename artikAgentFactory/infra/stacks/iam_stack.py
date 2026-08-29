"""Least-privilege IAM roles, one per component, per the approved plan §17 — no
wildcard permissions, no shared "do everything" role. Application code (web + worker)
assumes these via ECS task roles, never long-lived access keys."""
from __future__ import annotations

from aws_cdk import Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import aws_sqs as sqs
from constructs import Construct

from env_config import EnvConfig


class IamStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, cfg: EnvConfig,
                run_queue: sqs.Queue, notify_queue: sqs.Queue, run_dlq: sqs.Queue, notify_dlq: sqs.Queue,
                exports_bucket: s3.Bucket,
                secrets: list[secretsmanager.Secret], db_credentials_secret: secretsmanager.Secret,
                **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        all_secrets = secrets + [db_credentials_secret]

        # ── ECS task EXECUTION role (pull image, write logs) — shared by web+worker,
        # this is infra plumbing, not app-level access, so sharing it is standard practice.
        self.task_execution_role = iam.Role(
            self, "TaskExecutionRole", role_name=f"{cfg.resource_prefix}-task-execution",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AmazonECSTaskExecutionRolePolicy")],
        )

        # ── Web task ROLE — app-level permissions for the FastAPI service ────────
        self.web_task_role = iam.Role(
            self, "WebTaskRole", role_name=f"{cfg.resource_prefix}-web-task",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )
        for s in all_secrets:
            s.grant_read(self.web_task_role)
        run_queue.grant_send_messages(self.web_task_role)      # enqueue manual "Run Now"
        notify_queue.grant_send_messages(self.web_task_role)   # not normally used directly, but symmetric/safe
        exports_bucket.grant_read_write(self.web_task_role)

        # ── Worker task ROLE — consumes both queues, runs the actual pipeline ────
        self.worker_task_role = iam.Role(
            self, "WorkerTaskRole", role_name=f"{cfg.resource_prefix}-worker-task",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )
        for s in all_secrets:
            s.grant_read(self.worker_task_role)
        run_queue.grant_consume_messages(self.worker_task_role)
        notify_queue.grant_consume_messages(self.worker_task_role)
        run_dlq.grant_consume_messages(self.worker_task_role)   # dead-letter inspection tooling, read-only intent
        notify_dlq.grant_consume_messages(self.worker_task_role)
        exports_bucket.grant_read_write(self.worker_task_role)

        # ── EventBridge Scheduler role — assumed by EventBridge Scheduler itself to
        # deliver a "run this agent" message onto the run queue. Scoped to exactly
        # one action on exactly one queue. ──────────────────────────────────────
        self.scheduler_role = iam.Role(
            self, "SchedulerRole", role_name=f"{cfg.resource_prefix}-eventbridge-scheduler",
            assumed_by=iam.ServicePrincipal("scheduler.amazonaws.com"),
        )
        run_queue.grant_send_messages(self.scheduler_role)

        # ── Database migration role — used by a one-off ECS task (CI/CD step), not
        # the long-running services, so it's separate and narrower (read access to
        # the DB secret + RDS connect, nothing else). ───────────────────────────
        self.migration_task_role = iam.Role(
            self, "MigrationTaskRole", role_name=f"{cfg.resource_prefix}-migration-task",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )
        db_credentials_secret.grant_read(self.migration_task_role)

        # ── Monitoring role — read-only, for any external dashboard/alerting tool
        # that isn't already covered by the CloudWatch console/IAM user access. ──
        self.monitoring_role = iam.Role(
            self, "MonitoringRole", role_name=f"{cfg.resource_prefix}-monitoring",
            assumed_by=iam.ServicePrincipal("cloudwatch.amazonaws.com"),
        )
