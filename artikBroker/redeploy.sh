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

"$(dirname "$0")/../artikAPIs/venv/bin/python" - "$IMG" "$REGION" <<'PY'
import os, sys, boto3
img, region = sys.argv[1], sys.argv[2]
ar = boto3.client("apprunner", region_name=region)
svc = next(s for s in ar.list_services()["ServiceSummaryList"] if s["ServiceName"] == "artikbroker")
d = ar.describe_service(ServiceArn=svc["ServiceArn"])["Service"]
sc, ic = d["SourceConfiguration"], d["InstanceConfiguration"]
ir = sc["ImageRepository"]; ir["ImageIdentifier"] = img
imgcfg = ir.setdefault("ImageConfiguration", {})

# Preserve existing plaintext env + Secrets Manager refs; additively ensure the
# per-user-auth vars. Existing secrets (APP_SECRET, API keys, …) are untouched.
envv = dict(imgcfg.get("RuntimeEnvironmentVariables", {}))
envv["ENVIRONMENT"] = "production"            # strict auth — no dev fallback admin
# Bootstrap admin only when provided (and only used the first time the users DB is
# empty). Pass via env to this script; it never has to live in the repo.
if os.environ.get("INITIAL_ADMIN_PASSWORD"):
    envv["INITIAL_ADMIN_PASSWORD"] = os.environ["INITIAL_ADMIN_PASSWORD"]
    envv["INITIAL_ADMIN_EMAIL"] = os.environ.get("INITIAL_ADMIN_EMAIL", "admin@artikbroker.local")
    envv["INITIAL_ADMIN_USERNAME"] = os.environ.get("INITIAL_ADMIN_USERNAME", "admin")
# Agent-completion notifications → Artik Notifier. Set additively when provided via the
# deployer env (the API key is a secret, never in the repo); preserved across redeploys.
for _k in ("NOTIFICATIONS_ENABLED", "ARTIK_NOTIFY_API_URL", "ARTIK_NOTIFY_API_KEY",
           "ARTIK_BROKER_APP_NAME", "ARTIK_BROKER_BASE_URL"):
    if os.environ.get(_k):
        envv[_k] = os.environ[_k]
imgcfg["RuntimeEnvironmentVariables"] = envv

ar.update_service(
    ServiceArn=svc["ServiceArn"],
    SourceConfiguration={
        "AuthenticationConfiguration": sc["AuthenticationConfiguration"],
        "AutoDeploymentsEnabled": sc.get("AutoDeploymentsEnabled", False),
        "ImageRepository": ir,
    },
    InstanceConfiguration={"Cpu": ic["Cpu"], "Memory": ic["Memory"], "InstanceRoleArn": ic["InstanceRoleArn"]},
)
secs = sorted(imgcfg.get("RuntimeEnvironmentSecrets", {}).keys())
print("✅ submitted. secrets preserved:", secs)
print("   plaintext env:", sorted(envv.keys()))
if not os.environ.get("INITIAL_ADMIN_PASSWORD") and "INITIAL_ADMIN_PASSWORD" not in envv:
    print("   ⚠ INITIAL_ADMIN_PASSWORD not set and not already on the service — startup will FAIL "
          "in production until you set it. Re-run with INITIAL_ADMIN_PASSWORD=...")
print("   URL: https://" + svc["ServiceUrl"])
PY
