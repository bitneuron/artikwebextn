#!/usr/bin/env bash
# Deploy Artik Notifier (combined API + SPA image) to AWS App Runner.
# Builds the image, pushes to ECR, and creates/updates the "artik-notifier" service.
# Run from artikNotifier/:  ./deploy.sh
set -euo pipefail
cd "$(dirname "$0")"

REGION="${AWS_REGION:-us-west-2}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
ECR="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"
REPO="artik-notifier"
TAG="v$(date +%Y%m%d%H%M%S)"
IMG="${ECR}/${REPO}:${TAG}"
ACCESS_ROLE="arn:aws:iam::${ACCOUNT}:role/AppRunnerECRAccessRole"
PY="../artikAPIs/venv/bin/python"

# A signing secret persists across redeploys; generate once if absent.
SECRET_KEY="${SECRET_KEY:-$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')}"

# ── Durable storage: Litestream replicates the SQLite DB to S3 so accounts/reminders
#    SURVIVE every redeploy (App Runner has no persistent disk). ────────────────────
BUCKET="artik-notifier-db-${ACCOUNT}"
INSTANCE_ROLE="ArtikNotifierInstanceRole"
INSTANCE_ROLE_ARN="arn:aws:iam::${ACCOUNT}:role/${INSTANCE_ROLE}"

echo "▶ Ensuring S3 bucket ${BUCKET} (versioned, private)"
if ! aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
    --create-bucket-configuration LocationConstraint="$REGION" >/dev/null
fi
aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true >/dev/null
aws s3api put-bucket-versioning --bucket "$BUCKET" \
  --versioning-configuration Status=Enabled >/dev/null   # recover from accidental deletion

echo "▶ Ensuring App Runner instance role ${INSTANCE_ROLE} (S3 access for Litestream)"
if ! aws iam get-role --role-name "$INSTANCE_ROLE" >/dev/null 2>&1; then
  aws iam create-role --role-name "$INSTANCE_ROLE" --assume-role-policy-document \
    '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"tasks.apprunner.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
fi
aws iam put-role-policy --role-name "$INSTANCE_ROLE" --policy-name litestream-s3 \
  --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"s3:GetObject\",\"s3:PutObject\",\"s3:DeleteObject\",\"s3:ListBucket\"],\"Resource\":[\"arn:aws:s3:::${BUCKET}\",\"arn:aws:s3:::${BUCKET}/*\"]}]}" >/dev/null

echo "▶ Ensuring ECR repo ${REPO}"
aws ecr describe-repositories --region "$REGION" --repository-names "$REPO" >/dev/null 2>&1 \
  || aws ecr create-repository --region "$REGION" --repository-name "$REPO" >/dev/null

echo "▶ Building ${IMG} (linux/amd64)"
docker build --platform linux/amd64 -f Dockerfile -t "${REPO}:latest" .
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ECR" >/dev/null
docker tag "${REPO}:latest" "$IMG"
docker push "$IMG" >/dev/null
echo "▶ Pushed ${TAG}"

SECRET_KEY="$SECRET_KEY" IMG="$IMG" REGION="$REGION" ACCESS_ROLE="$ACCESS_ROLE" REPO="$REPO" \
BUCKET="$BUCKET" INSTANCE_ROLE_ARN="$INSTANCE_ROLE_ARN" \
"$PY" - <<'PY'
import os, time, boto3
img, region, repo = os.environ["IMG"], os.environ["REGION"], os.environ["REPO"]
access_role, secret_key = os.environ["ACCESS_ROLE"], os.environ["SECRET_KEY"]
bucket, instance_role = os.environ["BUCKET"], os.environ["INSTANCE_ROLE_ARN"]
# Litestream needs these set on the container so the entrypoint restores/replicates.
litestream_env = {"LITESTREAM_BUCKET": bucket, "LITESTREAM_REGION": region}
ar = boto3.client("apprunner", region_name=region)

# Single-instance autoscaling (SQLite is on the instance FS → keep it to one).
asc_name = "artik-notifier-single"
asc = next((c for c in ar.list_auto_scaling_configurations(AutoScalingConfigurationName=asc_name)
            .get("AutoScalingConfigurationSummaryList", [])), None)
if asc:
    asc_arn = asc["AutoScalingConfigurationArn"]
else:
    asc_arn = ar.create_auto_scaling_configuration(
        AutoScalingConfigurationName=asc_name, MaxConcurrency=100, MinSize=1, MaxSize=1
    )["AutoScalingConfiguration"]["AutoScalingConfigurationArn"]
print("autoscaling:", asc_arn.split('/')[-2])

svc = next((s for s in ar.list_services()["ServiceSummaryList"] if s["ServiceName"] == "artik-notifier"), None)

if svc:
    d = ar.describe_service(ServiceArn=svc["ServiceArn"])["Service"]
    sc, ic = d["SourceConfiguration"], d["InstanceConfiguration"]
    ir = sc["ImageRepository"]; ir["ImageIdentifier"] = img        # preserve existing env vars
    cfg = ir.setdefault("ImageConfiguration", {})
    env = cfg.get("RuntimeEnvironmentVariables", {}) or {}
    env.update(litestream_env)                                     # add/refresh Litestream vars
    cfg["RuntimeEnvironmentVariables"] = env
    ar.update_service(
        ServiceArn=svc["ServiceArn"],
        SourceConfiguration={
            "AuthenticationConfiguration": sc["AuthenticationConfiguration"],
            "AutoDeploymentsEnabled": False, "ImageRepository": ir},
        # Attach the instance role so the container can reach S3 (Litestream).
        InstanceConfiguration={"Cpu": ic["Cpu"], "Memory": ic["Memory"],
                               "InstanceRoleArn": instance_role})
    url = svc["ServiceUrl"]
    print("✅ updated existing service (Litestream S3 persistence)")
else:
    resp = ar.create_service(
        ServiceName="artik-notifier",
        SourceConfiguration={
            "AuthenticationConfiguration": {"AccessRoleArn": access_role},
            "AutoDeploymentsEnabled": False,
            "ImageRepository": {
                "ImageIdentifier": img,
                "ImageRepositoryType": "ECR",
                "ImageConfiguration": {
                    "Port": "8080",
                    "RuntimeEnvironmentVariables": {
                        "ENVIRONMENT": "production",
                        "SECRET_KEY": secret_key,
                        "SCHEDULER_ENABLED": "true",
                        "SCHEDULER_INTERVAL_MINUTES": "60",
                        "COOKIE_SECURE": "true",
                        **litestream_env,
                    },
                },
            },
        },
        InstanceConfiguration={"Cpu": "1 vCPU", "Memory": "2 GB",
                               "InstanceRoleArn": instance_role},
        AutoScalingConfigurationArn=asc_arn,
        HealthCheckConfiguration={"Protocol": "HTTP", "Path": "/api/health",
                                  "Interval": 10, "Timeout": 5,
                                  "HealthyThreshold": 1, "UnhealthyThreshold": 5},
    )
    url = resp["Service"]["ServiceUrl"]
    print("✅ created service artik-notifier")

print("   URL: https://" + url)
PY
