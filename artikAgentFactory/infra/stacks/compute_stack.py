"""ECS Fargate: one `web` service behind a public ALB, and one `run-worker` service
sharing the same image with a different CMD (`WORKER_ROLE=run`) — this is the durable-
queue execution path from the approved plan §11/19. The web service never runs
`execute_run()` inline in this mode; only the run-worker does, pulled from SQS. Slack
delivery happens synchronously inside `execute_run()` (see pipeline/alerts.py), so
there is no separate notify-worker — notify_queue/notify_dlq are provisioned in
DataStack for a possible future decoupled-notification iteration but have no consumer
here yet."""
from __future__ import annotations

from aws_cdk import Duration, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import aws_sqs as sqs
from constructs import Construct

from env_config import EnvConfig


class ComputeStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, cfg: EnvConfig,
                vpc: ec2.Vpc, alb_sg: ec2.SecurityGroup, ecs_web_sg: ec2.SecurityGroup,
                ecs_worker_sg: ec2.SecurityGroup, task_execution_role: iam.Role,
                web_task_role: iam.Role, worker_task_role: iam.Role,
                database_endpoint: str, database_port: str, database_name: str,
                db_credentials_secret: secretsmanager.Secret, run_queue: sqs.Queue, notify_queue: sqs.Queue,
                app_secret: secretsmanager.Secret, anthropic_secret: secretsmanager.Secret,
                initial_admin_password_secret: secretsmanager.Secret, repository: ecr.IRepository,
                log_group: logs.LogGroup, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.repository = repository  # shared across environments — see registry_stack.py

        self.cluster = ecs.Cluster(self, "Cluster", cluster_name=f"{cfg.resource_prefix}-cluster", vpc=vpc,
                                   container_insights=True)

        common_env = {
            "ENVIRONMENT": "production",
            "EXECUTION_BACKEND": "sqs", "SECRETS_BACKEND": "aws",
            # Display-only — a direct Slack Incoming Webhook, bound to its own channel
            # regardless of this value (see notify_client.py). SLACK_WEBHOOK_URL is NOT
            # injected here as a container env var — the app fetches it itself at
            # runtime via core/secrets.py's Secrets Manager lookup, gated on
            # SECRETS_PREFIX below matching the per-environment path data_stack.py
            # provisions it under.
            "SLACK_CHANNEL": cfg.slack_channel,
            "SECRETS_PREFIX": f"artikagentfactory/{cfg.env_name}",
            # First-boot bootstrap admin (see auth/bootstrap.py::ensure_initial_admin) —
            # email/username are fixed and not secret; the password comes from Secrets
            # Manager below and is force-reset on first login regardless.
            "INITIAL_ADMIN_EMAIL": f"admin@artikagentfactory-{cfg.env_name}.internal",
            "INITIAL_ADMIN_USERNAME": "admin",
            "RUN_QUEUE_URL": run_queue.queue_url, "NOTIFY_QUEUE_URL": notify_queue.queue_url,
            # Not secret — the app assembles DATABASE_URL from these plus the
            # DB_USERNAME/DB_PASSWORD secrets below at startup.
            "DB_HOST": database_endpoint, "DB_PORT": str(database_port), "DB_NAME": database_name,
        }
        common_secrets = {
            "APP_SECRET": ecs.Secret.from_secrets_manager(app_secret),
            # Unlike SLACK_WEBHOOK_URL, the research pipeline reads ANTHROPIC_API_KEY
            # straight from os.environ with no Secrets-Manager fallback (see
            # services/model_config.py::get_anthropic_api_key) — it must be injected as
            # a real container env var here.
            "ANTHROPIC_API_KEY": ecs.Secret.from_secrets_manager(anthropic_secret),
            "INITIAL_ADMIN_PASSWORD": ecs.Secret.from_secrets_manager(initial_admin_password_secret),
            "DB_USERNAME": ecs.Secret.from_secrets_manager(db_credentials_secret, "username"),
            "DB_PASSWORD": ecs.Secret.from_secrets_manager(db_credentials_secret, "password"),
        }

        image = ecs.ContainerImage.from_ecr_repository(self.repository, tag="latest")

        # ── Web service (FastAPI, behind the ALB) ────────────────────────────────
        web_task = ecs.FargateTaskDefinition(
            self, "WebTaskDef", family=f"{cfg.resource_prefix}-web",
            cpu=512, memory_limit_mib=1024,
            execution_role=task_execution_role, task_role=web_task_role,
        )
        web_task.add_container(
            "web", image=image, port_mappings=[ecs.PortMapping(container_port=8420)],
            environment={**common_env, "WORKER_ROLE": ""},
            secrets=common_secrets,
            logging=ecs.LogDrivers.aws_logs(stream_prefix="web", log_group=log_group),
            health_check=ecs.HealthCheck(command=["CMD-SHELL", "curl -f http://localhost:8420/api/health || exit 1"]),
        )
        self.web_service = ecs.FargateService(
            self, "WebService", cluster=self.cluster, task_definition=web_task,
            desired_count=cfg.web_min_tasks, security_groups=[ecs_web_sg],
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            min_healthy_percent=100, max_healthy_percent=200,
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
        )
        self.web_service.auto_scale_task_count(min_capacity=cfg.web_min_tasks, max_capacity=cfg.web_max_tasks) \
            .scale_on_cpu_utilization("WebCpuScaling", target_utilization_percent=60)

        # ── ALB (public entry point) ─────────────────────────────────────────────
        self.alb = elbv2.ApplicationLoadBalancer(
            self, "Alb", vpc=vpc, internet_facing=True, security_group=alb_sg,
            load_balancer_name=f"{cfg.resource_prefix}-alb"[:32],
        )
        # Plain HTTP at the ALB — CloudFront (edge_stack.py) terminates public HTTPS
        # with its own cert and talks to this ALB over the AWS backbone. An ACM cert
        # ON the ALB (for CloudFront->ALB TLS too) needs a real domain name, which is
        # deliberately deferred (see the approved plan's domain-gated deferral) —
        # this listener is what lets `cdk synth` succeed without one; upgrading to
        # HTTPS here later is additive, not a rearchitecture.
        listener = self.alb.add_listener("HttpListener", port=80, open=False)
        listener.add_targets(
            "WebTargets", port=8420, protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[self.web_service], health_check=elbv2.HealthCheck(path="/api/health"),
        )

        # ── Run worker — consumes agent-run-queue, calls the SAME unmodified
        # execute_run() as local/manual runs (see backend/app/worker/main.py). Slack
        # delivery happens synchronously INSIDE execute_run() today (see
        # pipeline/alerts.py::deliver_alert_events, called post-finalize) rather than
        # through a separate decoupled notify-worker — notify_queue/notify_dlq are
        # provisioned in DataStack for a future decoupled-notification iteration but
        # deliberately have no consumer here yet, so this stack doesn't stand up idle,
        # non-functional infrastructure to match an unimplemented code path.
        worker_task = ecs.FargateTaskDefinition(
            self, "RunWorkerTaskDef", family=f"{cfg.resource_prefix}-run-worker",
            cpu=512, memory_limit_mib=1024,
            execution_role=task_execution_role, task_role=worker_task_role,
        )
        worker_task.add_container(
            "run_worker", image=image,
            environment={**common_env, "WORKER_ROLE": "run"},
            secrets=common_secrets,
            logging=ecs.LogDrivers.aws_logs(stream_prefix="run-worker", log_group=log_group),
        )
        self.run_worker_service = ecs.FargateService(
            self, "RunWorkerService", cluster=self.cluster, task_definition=worker_task,
            desired_count=cfg.worker_min_tasks, security_groups=[ecs_worker_sg],
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            min_healthy_percent=100, max_healthy_percent=200,
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
        )
        self.run_worker_service.auto_scale_task_count(min_capacity=cfg.worker_min_tasks, max_capacity=cfg.worker_max_tasks) \
            .scale_on_metric(
                "RunWorkerQueueDepthScaling",
                metric=run_queue.metric_approximate_number_of_messages_visible(period=Duration.minutes(1)),
                scaling_steps=[
                    {"upper": 0, "change": -1}, {"lower": 1, "change": 0}, {"lower": 10, "change": +1},
                ],
            )
