#!/usr/bin/env bash
# One-shot deploy of artikBroker to AWS App Runner (container via ECR).
# Run from the SUPERPROJECT ROOT:  ./artikBroker/deploy.sh
# Prereqs: Docker daemon running, AWS CLI authenticated.
set -euo pipefail

# ── Config ───────────────────────────────────────────────────────────────────
REGION="${AWS_REGION:-us-west-2}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
REPO="artikbroker"
SERVICE="artikbroker"
TAG="${TAG:-latest}"
ECR="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"
IMAGE="${ECR}/${REPO}:${TAG}"
CPU="1024"      # 1 vCPU
MEMORY="2048"   # 2 GB (pandas/numpy/yfinance)

echo "▶ Account=${ACCOUNT} Region=${REGION} Image=${IMAGE}"

# ── 1. Build the image (from repo root so engine + app are both in context) ───
echo "▶ Building image..."
docker build --platform linux/amd64 -f artikBroker/Dockerfile -t "${REPO}:${TAG}" .

# ── 2. ECR repo (create if missing) ──────────────────────────────────────────
aws ecr describe-repositories --repository-names "${REPO}" --region "${REGION}" >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name "${REPO}" --region "${REGION}" >/dev/null
echo "▶ ECR repo ready: ${REPO}"

# ── 3. Push ──────────────────────────────────────────────────────────────────
aws ecr get-login-password --region "${REGION}" | docker login --username AWS --password-stdin "${ECR}"
docker tag "${REPO}:${TAG}" "${IMAGE}"
docker push "${IMAGE}"
echo "▶ Pushed ${IMAGE}"

# ── 4. IAM role so App Runner can pull from ECR ──────────────────────────────
ROLE="AppRunnerECRAccessRole"
if ! aws iam get-role --role-name "${ROLE}" >/dev/null 2>&1; then
  echo "▶ Creating ${ROLE}..."
  aws iam create-role --role-name "${ROLE}" \
    --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"build.apprunner.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  aws iam attach-role-policy --role-name "${ROLE}" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess >/dev/null
  sleep 10  # let the role propagate
fi
ROLE_ARN="arn:aws:iam::${ACCOUNT}:role/${ROLE}"

# ── 5. Runtime env vars (AI Search keys + per-user auth) ─────────────────────
# Keys from your shell or artikAgents/.env. Auth is now per-user (DB-backed):
# ENVIRONMENT=production turns on strict auth, APP_SECRET signs session cookies,
# and INITIAL_ADMIN_* bootstraps the first admin on a fresh DB. APP_PASSWORD is
# deprecated (the old single shared gate is no longer used).
KEY="${ANTHROPIC_API_KEY:-$(grep -h '^ANTHROPIC_API_KEY=' artikAgents/agents/.env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"'"'")}"
OKEY="${OPENAI_API_KEY:-$(grep -h '^OPENAI_API_KEY=' artikAgents/agents/.env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"'"'")}"
ENV_PAIRS=""
[ -n "${KEY}" ]   && ENV_PAIRS="\"ANTHROPIC_API_KEY\":\"${KEY}\""
[ -n "${OKEY}" ]  && ENV_PAIRS="${ENV_PAIRS:+${ENV_PAIRS},}\"OPENAI_API_KEY\":\"${OKEY}\""
# Production auth (strict): no dev open-mode, no dev fallback admin.
ENV_PAIRS="${ENV_PAIRS:+${ENV_PAIRS},}\"ENVIRONMENT\":\"production\""
# Cookie-signing secret: reuse APP_SECRET from env, else mint a fresh one.
APP_SECRET="${APP_SECRET:-$(python3 -c 'import os;print(os.urandom(32).hex())')}"
ENV_PAIRS="${ENV_PAIRS},\"APP_SECRET\":\"${APP_SECRET}\""
# Bootstrap admin (only used the first time the users DB is empty).
if [ -n "${INITIAL_ADMIN_PASSWORD:-}" ]; then
  IA_EMAIL="${INITIAL_ADMIN_EMAIL:-admin@artikbroker.local}"
  IA_USER="${INITIAL_ADMIN_USERNAME:-admin}"
  ENV_PAIRS="${ENV_PAIRS},\"INITIAL_ADMIN_EMAIL\":\"${IA_EMAIL}\",\"INITIAL_ADMIN_USERNAME\":\"${IA_USER}\",\"INITIAL_ADMIN_PASSWORD\":\"${INITIAL_ADMIN_PASSWORD}\""
fi
RTE=""; [ -n "${ENV_PAIRS}" ] && RTE=",\"RuntimeEnvironmentVariables\":{${ENV_PAIRS}}"
[ -z "${INITIAL_ADMIN_PASSWORD:-}" ] && echo "⚠ INITIAL_ADMIN_PASSWORD not set — if the users DB is empty the app will FAIL to start in production. Re-run with INITIAL_ADMIN_PASSWORD=... (and optional INITIAL_ADMIN_EMAIL / INITIAL_ADMIN_USERNAME)."
echo "ℹ Note: the SQLite users DB lives on the container filesystem (USERS_DB_PATH, default config/users.db). On App Runner this resets on redeploy — point USERS_DB_PATH at a persistent mount (EFS) to retain user-created accounts across deploys."
[ -z "${KEY}${OKEY}" ] && echo "⚠ No ANTHROPIC_API_KEY or OPENAI_API_KEY — AI Search will be disabled on the deploy."

SRC_CONFIG="{
  \"AuthenticationConfiguration\": {\"AccessRoleArn\": \"${ROLE_ARN}\"},
  \"AutoDeploymentsEnabled\": true,
  \"ImageRepository\": {
    \"ImageIdentifier\": \"${IMAGE}\",
    \"ImageRepositoryType\": \"ECR\",
    \"ImageConfiguration\": {\"Port\": \"8080\"${RTE}}
  }
}"

# ── 6. Create the service, or update it (applies new image + env vars) ────────
SERVICE_ARN="$(aws apprunner list-services --region "${REGION}" \
  --query "ServiceSummaryList[?ServiceName=='${SERVICE}'].ServiceArn" --output text)"

if [ -z "${SERVICE_ARN}" ]; then
  echo "▶ Creating App Runner service '${SERVICE}'..."
  aws apprunner create-service --region "${REGION}" \
    --service-name "${SERVICE}" \
    --source-configuration "${SRC_CONFIG}" \
    --instance-configuration "{\"Cpu\": \"${CPU}\", \"Memory\": \"${MEMORY}\"}" \
    --health-check-configuration '{"Protocol":"TCP","Interval":10,"Timeout":5,"HealthyThreshold":1,"UnhealthyThreshold":5}' \
    >/dev/null
  echo "▶ Service creating — this takes a few minutes."
else
  echo "▶ Service exists; updating image + env vars (triggers a deployment)..."
  aws apprunner update-service --region "${REGION}" --service-arn "${SERVICE_ARN}" \
    --source-configuration "${SRC_CONFIG}" >/dev/null
fi

# ── 7. Show the URL ──────────────────────────────────────────────────────────
echo "▶ Waiting for service URL..."
for _ in $(seq 1 30); do
  URL="$(aws apprunner list-services --region "${REGION}" \
    --query "ServiceSummaryList[?ServiceName=='${SERVICE}'].ServiceUrl" --output text)"
  [ -n "${URL}" ] && [ "${URL}" != "None" ] && break
  sleep 5
done
echo "✅ Deployed. https://${URL}"
echo "   (First create takes ~5-10 min to reach RUNNING; check the App Runner console.)"
