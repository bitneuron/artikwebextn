#!/usr/bin/env bash
# Ship a CODE change to the existing artikBroker App Runner service.
# Builds a new image (immutable tag), pushes to ECR, and updates the service
# swapping ONLY the image — preserving the Secrets Manager refs + IAM roles.
# Use this (not deploy.sh) now that secrets live in Secrets Manager.
# Run from the SUPERPROJECT ROOT:  ./artikBroker/redeploy.sh
set -euo pipefail
REGION="${AWS_REGION:-us-west-2}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
ECR="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"
TAG="v$(date +%Y%m%d%H%M%S)"
IMG="${ECR}/artikbroker:${TAG}"

echo "▶ Building ${IMG}"
docker build --platform linux/amd64 -f artikBroker/Dockerfile -t artikbroker:latest .
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ECR" >/dev/null
docker tag artikbroker:latest "$IMG"
docker push "$IMG" >/dev/null
echo "▶ Pushed ${TAG}; updating service (image only, secrets/roles preserved)"

python3 - "$IMG" "$REGION" <<'PY'
import sys, boto3
img, region = sys.argv[1], sys.argv[2]
ar = boto3.client("apprunner", region_name=region)
svc = next(s for s in ar.list_services()["ServiceSummaryList"] if s["ServiceName"] == "artikbroker")
d = ar.describe_service(ServiceArn=svc["ServiceArn"])["Service"]
sc, ic = d["SourceConfiguration"], d["InstanceConfiguration"]
ir = sc["ImageRepository"]; ir["ImageIdentifier"] = img
ar.update_service(
    ServiceArn=svc["ServiceArn"],
    SourceConfiguration={
        "AuthenticationConfiguration": sc["AuthenticationConfiguration"],
        "AutoDeploymentsEnabled": sc.get("AutoDeploymentsEnabled", False),
        "ImageRepository": ir,
    },
    InstanceConfiguration={"Cpu": ic["Cpu"], "Memory": ic["Memory"], "InstanceRoleArn": ic["InstanceRoleArn"]},
)
secs = sorted(ir["ImageConfiguration"].get("RuntimeEnvironmentSecrets", {}).keys())
print("✅ submitted. secrets preserved:", secs, "| plaintext:", sorted(ir["ImageConfiguration"].get("RuntimeEnvironmentVariables", {}).keys()) or "NONE")
print("   URL: https://" + svc["ServiceUrl"])
PY
