"""CloudFront + WAF in front of the ALB, plus Route53/ACM when a real domain is
configured. Domain-gated per the approved plan §14: without `cfg.domain_name` set,
this stack still creates CloudFront + WAF (using the ALB's default DNS name as
origin) but skips ACM/Route53 — a custom domain is a deferred, explicit user
decision, never fabricated.

When cfg.enable_cloudfront is True, the WAF WebACL is NOT created here — a
CLOUDFRONT-scope WebACL can only be created in us-east-1 (a hard AWS constraint), so
it comes from a separate CloudFrontWafStack (see cloudfront_waf_stack.py) via
`web_acl_arn`, wired up in app.py with CDK's cross_region_references mechanism. The
REGIONAL-scope case (cfg.enable_cloudfront False, e.g. staging) has no such
constraint and is still built in-region here."""
from __future__ import annotations

from aws_cdk import Stack
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as route53_targets
from aws_cdk import aws_wafv2 as wafv2
from constructs import Construct

from env_config import EnvConfig


class EdgeStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, cfg: EnvConfig,
                alb: elbv2.ApplicationLoadBalancer, web_acl_arn: str | None = None, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # CLOUDFRONT-scope ACL arrives pre-built from CloudFrontWafStack (us-east-1).
        self.web_acl_arn = web_acl_arn
        if cfg.enable_waf and not cfg.enable_cloudfront:
            self.web_acl = wafv2.CfnWebACL(
                self, "WebAcl", scope="REGIONAL",
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

        certificate = None
        hosted_zone = None
        if cfg.domain_name:
            hosted_zone = route53.HostedZone.from_lookup(self, "HostedZone", domain_name=cfg.domain_name)
            certificate = acm.Certificate(
                self, "Certificate", domain_name=cfg.domain_name,
                validation=acm.CertificateValidation.from_dns(hosted_zone),
            )

        if cfg.enable_cloudfront:
            self.distribution = cloudfront.Distribution(
                self, "Distribution",
                default_behavior=cloudfront.BehaviorOptions(
                    # HTTP to the ALB (see compute_stack.py) — CloudFront still
                    # terminates the public-facing side with its own cert per
                    # viewer_protocol_policy below; upgrade to HTTPS_ONLY once the
                    # ALB has a real ACM cert (needs a domain, deliberately deferred).
                    origin=origins.LoadBalancerV2Origin(alb, protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY),
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,  # dynamic API + app, not a static site
                    # Without an origin request policy, CloudFront's default forwards
                    # no cookies/most headers to the origin AND strips Set-Cookie from
                    # the response on the way back — breaks the session-cookie login
                    # flow entirely. ALL_VIEWER forwards everything through unmodified,
                    # matching a pure reverse-proxy in front of a dynamic app.
                    origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER,
                ),
                domain_names=[cfg.domain_name] if cfg.domain_name else None,
                certificate=certificate,
                web_acl_id=self.web_acl_arn,
            )
            if cfg.domain_name and hosted_zone:
                route53.ARecord(
                    self, "AliasRecord", zone=hosted_zone,
                    target=route53.RecordTarget.from_alias(route53_targets.CloudFrontTarget(self.distribution)),
                )
