"""CloudWatch alarms for the signal list in the approved plan §20, an SNS topic to
notify on alarm, and CloudTrail for AWS API auditing (distinct from the app's own
`audit_events` table — this is infrastructure-level auditing)."""
from __future__ import annotations

from aws_cdk import Duration, Stack
from aws_cdk import aws_cloudtrail as cloudtrail
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_rds as rds
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sqs as sqs
from constructs import Construct

from env_config import EnvConfig


class ObservabilityStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, cfg: EnvConfig,
                web_service: ecs.FargateService, database: rds.DatabaseInstance,
                run_queue: sqs.Queue, notify_queue: sqs.Queue,
                run_dlq: sqs.Queue, notify_dlq: sqs.Queue, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.alarm_topic = sns.Topic(self, "AlarmTopic", topic_name=f"{cfg.resource_prefix}-alarms")

        def _alarm(id_: str, metric: cloudwatch.Metric, *, threshold: float, evaluation_periods: int = 2,
                  comparison=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD) -> cloudwatch.Alarm:
            alarm = cloudwatch.Alarm(
                self, id_, metric=metric, threshold=threshold, evaluation_periods=evaluation_periods,
                comparison_operator=comparison, treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            )
            alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))
            return alarm

        # ── Application availability / errors ────────────────────────────────────
        _alarm("WebServiceUnhealthy",
              web_service.metric_cpu_utilization(period=Duration.minutes(5)), threshold=90)

        # ── Queue health: depth, oldest message age, dead-letter arrivals ────────
        _alarm("RunQueueDepth", run_queue.metric_approximate_number_of_messages_visible(period=Duration.minutes(5)),
              threshold=50)
        _alarm("RunQueueOldestMessage", run_queue.metric_approximate_age_of_oldest_message(period=Duration.minutes(5)),
              threshold=600)  # 10 min — a run shouldn't sit unclaimed that long
        _alarm("RunDlqNotEmpty", run_dlq.metric_approximate_number_of_messages_visible(period=Duration.minutes(5)),
              threshold=0, evaluation_periods=1)
        _alarm("NotifyDlqNotEmpty", notify_dlq.metric_approximate_number_of_messages_visible(period=Duration.minutes(5)),
              threshold=0, evaluation_periods=1)

        # ── Database health ───────────────────────────────────────────────────────
        _alarm("DatabaseHighCpu", database.metric_cpu_utilization(period=Duration.minutes(5)), threshold=80)
        _alarm("DatabaseLowStorage", database.metric_free_storage_space(period=Duration.minutes(5)),
              threshold=2_000_000_000, comparison=cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD)
        _alarm("DatabaseHighConnections", database.metric_database_connections(period=Duration.minutes(5)),
              threshold=80)

        # NOTE: application-level signals (login failures, authorization denials,
        # search-provider failures, Slack-delivery failures, repeated scheduler
        # failures) are emitted as structured JSON logs (core/logging_config.py) —
        # CloudWatch Logs Metric Filters turning those into alarm-able metrics are a
        # follow-up once real log volume/patterns from a running deployment are
        # available to tune thresholds against; listed here so the gap is visible,
        # not silently dropped.

        # ── CloudTrail: AWS API auditing (account-level, not org-wide — see the
        # approved plan's explicit note that org-wide CloudTrail scope is an
        # organizational decision outside this app's remit) ─────────────────────
        cloudtrail.Trail(
            self, "Trail", trail_name=f"{cfg.resource_prefix}-trail",
            is_multi_region_trail=False, enable_file_validation=True,
            send_to_cloud_watch_logs=True,
        )
