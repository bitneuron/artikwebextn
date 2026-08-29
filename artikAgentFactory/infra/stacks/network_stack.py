"""VPC: 2 AZs, public subnets ONLY for the ALB + NAT gateways, private subnets for
ECS tasks and RDS. No public RDS access. Security groups are least-privilege:
ALB accepts HTTP from the internet (CloudFront terminates public HTTPS and talks to
the ALB over the AWS backbone — see compute_stack.py), ECS web accepts traffic only
from the ALB SG, RDS accepts traffic only from the ECS SGs."""
from __future__ import annotations

from aws_cdk import Stack
from aws_cdk import aws_ec2 as ec2
from constructs import Construct

from env_config import EnvConfig


class NetworkStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, cfg: EnvConfig, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.vpc = ec2.Vpc(
            self, "Vpc",
            vpc_name=f"{cfg.resource_prefix}-vpc",
            max_azs=2,
            nat_gateways=1 if cfg.env_name == "staging" else 2,  # staging: one NAT to save cost
            subnet_configuration=[
                ec2.SubnetConfiguration(name="public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24),
                ec2.SubnetConfiguration(name="private-ecs", subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS, cidr_mask=24),
                ec2.SubnetConfiguration(name="private-data", subnet_type=ec2.SubnetType.PRIVATE_ISOLATED, cidr_mask=24),
            ],
        )

        self.alb_sg = ec2.SecurityGroup(
            self, "AlbSecurityGroup", vpc=self.vpc, description="ALB - public entry point",
            security_group_name=f"{cfg.resource_prefix}-alb-sg", allow_all_outbound=True,
        )
        self.alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80), "HTTP from the internet / CloudFront")

        self.ecs_web_sg = ec2.SecurityGroup(
            self, "EcsWebSecurityGroup", vpc=self.vpc, description="Web tasks - traffic only from the ALB",
            security_group_name=f"{cfg.resource_prefix}-ecs-web-sg", allow_all_outbound=True,
        )
        self.ecs_web_sg.add_ingress_rule(self.alb_sg, ec2.Port.tcp(8420), "From ALB only")

        self.ecs_worker_sg = ec2.SecurityGroup(
            self, "EcsWorkerSecurityGroup", vpc=self.vpc, description="Worker tasks - no inbound needed",
            security_group_name=f"{cfg.resource_prefix}-ecs-worker-sg", allow_all_outbound=True,
        )

        self.db_sg = ec2.SecurityGroup(
            self, "DbSecurityGroup", vpc=self.vpc, description="RDS - private, ECS tasks only",
            security_group_name=f"{cfg.resource_prefix}-db-sg", allow_all_outbound=False,
        )
        self.db_sg.add_ingress_rule(self.ecs_web_sg, ec2.Port.tcp(5432), "Web tasks to Postgres")
        self.db_sg.add_ingress_rule(self.ecs_worker_sg, ec2.Port.tcp(5432), "Worker tasks to Postgres")

        # VPC endpoints so ECS/RDS traffic to AWS services (Secrets Manager, ECR,
        # CloudWatch Logs, SQS) never needs to traverse the NAT gateway.
        self.vpc.add_interface_endpoint("SecretsManagerEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER)
        self.vpc.add_interface_endpoint("CloudWatchLogsEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS)
        self.vpc.add_interface_endpoint("SqsEndpoint", service=ec2.InterfaceVpcEndpointAwsService.SQS)
        self.vpc.add_gateway_endpoint("S3Endpoint", service=ec2.GatewayVpcEndpointAwsService.S3)
