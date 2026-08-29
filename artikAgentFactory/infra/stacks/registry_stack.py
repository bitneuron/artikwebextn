"""ONE shared ECR repository, created once (not per-environment) — matches the CI/CD
principle of building a single immutable image and promoting the same tag from
staging to production rather than rebuilding per environment. Deliberately its own
tiny stack: creating it inside DataStack/ComputeStack for each environment would
either collide on the repository name (two stacks fighting over one physical
resource) or — the bug this was split out to fix — create a circular dependency,
since ECS's `ContainerImage.from_ecr_repository().bind()` implicitly grants ECR pull
on the task execution role (which lives in IamStack), and IamStack is upstream of
ComputeStack. Putting the repository in its own stack that's upstream of BOTH avoids
both problems."""
from __future__ import annotations

from aws_cdk import Stack
from aws_cdk import aws_ecr as ecr
from constructs import Construct


class RegistryStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.repository = ecr.Repository(
            self, "Repository", repository_name="artikagentfactory",
            image_scan_on_push=True,
            lifecycle_rules=[ecr.LifecycleRule(
                description="Keep the last 20 images, expire the rest",
                max_image_count=20,
            )],
        )
