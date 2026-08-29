"""RDS Postgres (private subnets, encrypted, automated backups, deletion protection
in prod), SQS run-queue + notify-queue (each with its own DLQ), an S3 exports bucket,
and Secrets Manager secret *shells* (empty placeholders the app reads via
core/secrets.py — real values are written by a human via the console/CLI, never by
CDK, so no secret material ever lives in a CloudFormation template or this repo)."""
from __future__ import annotations

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_kms as kms
from aws_cdk import aws_logs as logs
from aws_cdk import aws_rds as rds
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import aws_sqs as sqs
from constructs import Construct

from env_config import EnvConfig

# aws_logs.RetentionDays is an enum of specific supported values, not an arbitrary
# int — map the handful of day-counts env_config.py actually uses.
_RETENTION_BY_DAYS = {
    14: logs.RetentionDays.TWO_WEEKS,
    30: logs.RetentionDays.ONE_MONTH,
    90: logs.RetentionDays.THREE_MONTHS,
}


class DataStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, cfg: EnvConfig,
                vpc: ec2.Vpc, db_security_group: ec2.SecurityGroup, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Created here (upstream of both IamStack and ComputeStack) rather than in
        # ComputeStack — ECS's log-driver binding implicitly grants log-write
        # permissions on the task roles (which live in IamStack), which would
        # otherwise create the same circular-dependency shape documented in
        # registry_stack.py's docstring.
        self.log_group = logs.LogGroup(
            self, "AppLogGroup", log_group_name=f"/artikagentfactory/{cfg.env_name}",
            retention=_RETENTION_BY_DAYS.get(cfg.log_retention_days, logs.RetentionDays.ONE_MONTH),
            removal_policy=RemovalPolicy.RETAIN if cfg.env_name == "production" else RemovalPolicy.DESTROY,
        )

        # Customer-managed key, used ONLY for RDS storage encryption. RDS decrypts
        # storage transparently — the connecting application needs no KMS grant for
        # this, so it never crosses the IamStack boundary and can't create the
        # cross-stack cycle described below for the other resources.
        self.kms_key = kms.Key(
            self, "DataKmsKey", alias=f"{cfg.resource_prefix}-data",
            description="Encrypts RDS storage for artikAgentFactory",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.RETAIN if cfg.env_name == "production" else RemovalPolicy.DESTROY,
        )

        # Deliberately AWS-managed encryption (no `encryption_key=`) for every
        # resource below whose key would need to be granted to a role in IamStack:
        # KMS grant()/secret.grant_read() on a CUSTOMER-managed key updates the
        # key's OWN resource policy (in this stack) to reference the grantee role's
        # ARN (in IamStack) — while IamStack already depends on this stack for the
        # queue/bucket/secret ARNs themselves. That's a genuine bidirectional
        # relationship CloudFormation can't express as two stacks (confirmed
        # empirically — this is what produced the "DependencyCycle" errors here).
        # AWS-managed keys (`aws/secretsmanager`, `aws/sqs`, `aws/s3` — the default
        # when no key is specified) auto-authorize any principal with the
        # corresponding service-level IAM permission, so this is still real
        # encryption-at-rest, just without the cross-stack grant dance.

        # A manually-created, plain Secret (rather than
        # `rds.Credentials.from_generated_secret()`, which returns a special
        # SecretTargetAttachment construct with its own cross-stack-reference
        # quirks, confirmed independently problematic here too).
        self.db_credentials_secret = secretsmanager.Secret(
            self, "DbCredentialsSecret", secret_name=f"artikagentfactory/{cfg.env_name}/DATABASE_CREDENTIALS",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username": "agentfactory_app"}',
                generate_string_key="password", exclude_punctuation=True, password_length=32,
            ),
        )

        # ── RDS Postgres ──────────────────────────────────────────────────────
        self.database = rds.DatabaseInstance(
            self, "Database",
            instance_identifier=f"{cfg.resource_prefix}-db",
            engine=rds.DatabaseInstanceEngine.postgres(version=rds.PostgresEngineVersion.VER_16),
            instance_type=ec2.InstanceType(cfg.db_instance_class.replace("db.", "")),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[db_security_group],
            multi_az=cfg.db_multi_az,
            storage_encrypted=True,
            storage_encryption_key=self.kms_key,
            allocated_storage=20,
            max_allocated_storage=100,  # storage autoscaling, avoids manual resize ops
            backup_retention=Duration.days(14 if cfg.env_name == "production" else 3),
            deletion_protection=cfg.env_name == "production",
            removal_policy=RemovalPolicy.RETAIN if cfg.env_name == "production" else RemovalPolicy.DESTROY,
            credentials=rds.Credentials.from_secret(self.db_credentials_secret),
            database_name="artikagentfactory",
            enable_performance_insights=cfg.env_name == "production",
        )

        # ── SQS: agent runs + Slack notifications, each with its own DLQ ────────
        self.run_dlq = sqs.Queue(
            self, "AgentRunDlq", queue_name=f"{cfg.resource_prefix}-agent-run-dlq",
            encryption=sqs.QueueEncryption.KMS_MANAGED,
            retention_period=Duration.days(14),
        )
        self.run_queue = sqs.Queue(
            self, "AgentRunQueue", queue_name=f"{cfg.resource_prefix}-agent-run-queue",
            encryption=sqs.QueueEncryption.KMS_MANAGED,
            visibility_timeout=Duration.minutes(10),  # a run can take several minutes (real web-search calls)
            dead_letter_queue=sqs.DeadLetterQueue(max_receive_count=3, queue=self.run_dlq),
        )

        self.notify_dlq = sqs.Queue(
            self, "SlackNotifyDlq", queue_name=f"{cfg.resource_prefix}-slack-notify-dlq",
            encryption=sqs.QueueEncryption.KMS_MANAGED,
            retention_period=Duration.days(14),
        )
        self.notify_queue = sqs.Queue(
            self, "SlackNotifyQueue", queue_name=f"{cfg.resource_prefix}-slack-notify-queue",
            encryption=sqs.QueueEncryption.KMS_MANAGED,
            visibility_timeout=Duration.seconds(30),
            dead_letter_queue=sqs.DeadLetterQueue(max_receive_count=5, queue=self.notify_dlq),
        )

        # ── S3: approved exports (CSV/JSON result exports) ──────────────────────
        self.exports_bucket = s3.Bucket(
            self, "ExportsBucket", bucket_name=f"{cfg.resource_prefix}-exports-{cfg.account}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=True, enforce_ssl=True,
            lifecycle_rules=[s3.LifecycleRule(expiration=Duration.days(90), id="expire-old-exports")],
            removal_policy=RemovalPolicy.RETAIN if cfg.env_name == "production" else RemovalPolicy.DESTROY,
        )

        # ── Secrets Manager shells — CDK creates the named secret with a
        # placeholder value; a human overwrites it via `aws secretsmanager
        # put-secret-value` (or the console). CDK never sets real secret material. ──
        self.slack_webhook_url_secret = secretsmanager.Secret(
            self, "SlackWebhookUrlSecret", secret_name=f"artikagentfactory/{cfg.env_name}/SLACK_WEBHOOK_URL",
            description="Slack Incoming Webhook URL for this app's own #artik-agent-notify channel — "
                        "populate manually, CDK only reserves the name",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"placeholder": true}', generate_string_key="unused"),
            removal_policy=RemovalPolicy.RETAIN,
        )
        self.gmail_smtp_user_secret = secretsmanager.Secret(
            self, "GmailSmtpUserSecret", secret_name=f"artikagentfactory/{cfg.env_name}/GMAIL_SMTP_USER",
            description="Gmail address the Email Scheduler agent sends from — populate manually",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"placeholder": true}', generate_string_key="unused"),
            removal_policy=RemovalPolicy.RETAIN,
        )
        self.gmail_smtp_app_password_secret = secretsmanager.Secret(
            self, "GmailSmtpAppPasswordSecret",
            secret_name=f"artikagentfactory/{cfg.env_name}/GMAIL_SMTP_APP_PASSWORD",
            description="Gmail App Password (requires 2-Step Verification on that account) for the "
                        "Email Scheduler agent — populate manually, CDK only reserves the name",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"placeholder": true}', generate_string_key="unused"),
            removal_policy=RemovalPolicy.RETAIN,
        )
        self.anthropic_secret = secretsmanager.Secret(
            self, "AnthropicApiKeySecret", secret_name=f"artikagentfactory/{cfg.env_name}/ANTHROPIC_API_KEY",
            description="Anthropic API key for the research pipeline — populate manually",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"placeholder": true}', generate_string_key="unused"),
            removal_policy=RemovalPolicy.RETAIN,
        )
        self.app_secret = secretsmanager.Secret(
            self, "AppSecretSecret", secret_name=f"artikagentfactory/{cfg.env_name}/APP_SECRET",
            description="Session-signing secret — auto-generated by CDK, rotate via Secrets Manager if needed",
            generate_secret_string=secretsmanager.SecretStringGenerator(exclude_punctuation=False, password_length=64),
            removal_policy=RemovalPolicy.RETAIN,
        )
        self.initial_admin_password_secret = secretsmanager.Secret(
            self, "InitialAdminPasswordSecret",
            secret_name=f"artikagentfactory/{cfg.env_name}/INITIAL_ADMIN_PASSWORD",
            description="One-time bootstrap password for the 'admin' user (email/username fixed in "
                        "compute_stack.py's INITIAL_ADMIN_EMAIL/INITIAL_ADMIN_USERNAME env vars) — "
                        "auto-generated by CDK. ensure_initial_admin() forces a reset on first login, "
                        "so this value is only ever used once.",
            generate_secret_string=secretsmanager.SecretStringGenerator(exclude_punctuation=True, password_length=32),
            removal_policy=RemovalPolicy.RETAIN,
        )

        CfnOutput(self, "DatabaseEndpoint", value=self.database.db_instance_endpoint_address)
        CfnOutput(self, "ExportsBucketName", value=self.exports_bucket.bucket_name)
