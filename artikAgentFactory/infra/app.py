#!/usr/bin/env python3
"""CDK entry point. Instantiates a full stack set (network, data, iam, compute,
observability, edge) once per environment (staging, production), from one
`EnvConfig` each — see env_config.py. Deploying is a separate, explicit,
credential-gated step (`cdk deploy`); this file only defines what WOULD be created.
"""
from __future__ import annotations

import os

import aws_cdk as cdk

from env_config import production, staging
from stacks.cloudfront_waf_stack import CloudFrontWafStack
from stacks.compute_stack import ComputeStack
from stacks.data_stack import DataStack
from stacks.edge_stack import EdgeStack
from stacks.iam_stack import IamStack
from stacks.network_stack import NetworkStack
from stacks.observability_stack import ObservabilityStack
from stacks.registry_stack import RegistryStack

app = cdk.App()

# The account is read from the environment at synth/deploy time — never hardcoded —
# so this file is identical whether it's run against a sandbox or the real account.
account = os.environ.get("CDK_DEFAULT_ACCOUNT", "000000000000")
region = os.environ.get("CDK_DEFAULT_REGION", "us-west-2")

# ONE shared ECR repository across both environments — see registry_stack.py's
# docstring for why this can't live inside the per-environment stack sets.
registry = RegistryStack(app, "artikagentfactory-registry", env=cdk.Environment(account=account, region=region))


def build_stack_set(cfg) -> None:
    env = cdk.Environment(account=cfg.account, region=cfg.region)
    prefix = cfg.resource_prefix

    network = NetworkStack(app, f"{prefix}-network", cfg=cfg, env=env)
    cdk.Tags.of(network).add("Project", "artikAgentFactory")

    data = DataStack(app, f"{prefix}-data", cfg=cfg, vpc=network.vpc,
                     db_security_group=network.db_sg, env=env)

    iam_stack = IamStack(
        app, f"{prefix}-iam", cfg=cfg,
        run_queue=data.run_queue, notify_queue=data.notify_queue,
        run_dlq=data.run_dlq, notify_dlq=data.notify_dlq,
        exports_bucket=data.exports_bucket,
        secrets=[data.slack_webhook_url_secret, data.anthropic_secret, data.app_secret,
                data.initial_admin_password_secret,
                data.gmail_smtp_user_secret, data.gmail_smtp_app_password_secret],
        db_credentials_secret=data.db_credentials_secret, env=env,
    )

    compute = ComputeStack(
        app, f"{prefix}-compute", cfg=cfg, vpc=network.vpc,
        alb_sg=network.alb_sg, ecs_web_sg=network.ecs_web_sg, ecs_worker_sg=network.ecs_worker_sg,
        task_execution_role=iam_stack.task_execution_role,
        web_task_role=iam_stack.web_task_role, worker_task_role=iam_stack.worker_task_role,
        database_endpoint=data.database.db_instance_endpoint_address,
        database_port=data.database.db_instance_endpoint_port, database_name="artikagentfactory",
        db_credentials_secret=data.db_credentials_secret,
        run_queue=data.run_queue, notify_queue=data.notify_queue,
        app_secret=data.app_secret, anthropic_secret=data.anthropic_secret,
        initial_admin_password_secret=data.initial_admin_password_secret,
        repository=registry.repository, log_group=data.log_group, env=env,
    )

    ObservabilityStack(
        app, f"{prefix}-observability", cfg=cfg, web_service=compute.web_service, database=data.database,
        run_queue=data.run_queue, notify_queue=data.notify_queue,
        run_dlq=data.run_dlq, notify_dlq=data.notify_dlq, env=env,
    )

    # CLOUDFRONT-scope WAF ACLs can only be created in us-east-1 (hard AWS
    # constraint) — see cloudfront_waf_stack.py. Only needed when CloudFront itself
    # is enabled (production); staging builds its REGIONAL-scope ACL in-region
    # inside EdgeStack directly, with no cross-region wrinkle.
    web_acl_arn = None
    if cfg.enable_cloudfront and cfg.enable_waf:
        us_east_1_env = cdk.Environment(account=cfg.account, region="us-east-1")
        cf_waf = CloudFrontWafStack(app, f"{prefix}-cloudfront-waf", cfg=cfg, env=us_east_1_env,
                                    cross_region_references=True)
        web_acl_arn = cf_waf.web_acl_arn

    EdgeStack(app, f"{prefix}-edge", cfg=cfg, alb=compute.alb, web_acl_arn=web_acl_arn,
             env=env, cross_region_references=True if web_acl_arn else False)

    for stack in (network, data, iam_stack, compute):
        for key, value in cfg.tags.items():
            cdk.Tags.of(stack).add(key, value)


build_stack_set(staging(account=account))
build_stack_set(production(account=account))

app.synth()
