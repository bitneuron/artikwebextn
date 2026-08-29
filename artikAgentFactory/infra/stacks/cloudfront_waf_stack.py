"""A CLOUDFRONT-scope WAFv2 WebACL can only be created via the us-east-1 API,
regardless of which region the rest of the app (and CloudFront's own distribution
resource, which is a global service usable from any region's CloudFormation stack)
lives in — this is a hard AWS constraint, not a configuration choice. This stack
exists solely to satisfy that constraint: it's pinned to us-east-1 and deployed only
when cfg.enable_cloudfront is True, with its WebACL ARN passed into EdgeStack (in
cfg.region) via CDK's cross_region_references mechanism. Staging (enable_cloudfront=
False) never needs this — its REGIONAL-scope WebACL is created in-region by
EdgeStack directly, with no cross-region wrinkle."""
from __future__ import annotations

from aws_cdk import Stack
from aws_cdk import aws_wafv2 as wafv2
from constructs import Construct

from env_config import EnvConfig


class CloudFrontWafStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, cfg: EnvConfig, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.web_acl = wafv2.CfnWebACL(
            self, "WebAcl", scope="CLOUDFRONT",
            default_action=wafv2.CfnWebACL.DefaultActionProperty(allow={}),
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                sampled_requests_enabled=True, cloud_watch_metrics_enabled=True,
                metric_name=f"{cfg.resource_prefix}-waf"),
            rules=[
                wafv2.CfnWebACL.RuleProperty(
                    name="AWSManagedRulesCommonRuleSet", priority=0,
                    override_action=wafv2.CfnWebACL.OverrideActionProperty(none={}),
                    statement=wafv2.CfnWebACL.StatementProperty(
                        managed_rule_group_statement=wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                            vendor_name="AWS", name="AWSManagedRulesCommonRuleSet")),
                    visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                        sampled_requests_enabled=True, cloud_watch_metrics_enabled=True,
                        metric_name=f"{cfg.resource_prefix}-common"),
                ),
                wafv2.CfnWebACL.RuleProperty(
                    name="RateLimit", priority=1,
                    action=wafv2.CfnWebACL.RuleActionProperty(block={}),
                    statement=wafv2.CfnWebACL.StatementProperty(
                        rate_based_statement=wafv2.CfnWebACL.RateBasedStatementProperty(
                            limit=2000, aggregate_key_type="IP")),
                    visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                        sampled_requests_enabled=True, cloud_watch_metrics_enabled=True,
                        metric_name=f"{cfg.resource_prefix}-ratelimit"),
                ),
            ],
        )
        self.web_acl_arn = self.web_acl.attr_arn
