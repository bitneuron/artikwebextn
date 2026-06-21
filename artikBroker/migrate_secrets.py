"""One-off: move artikBroker's sensitive App Runner env vars into AWS Secrets Manager.

Reads the current plaintext RuntimeEnvironmentVariables, stores each in Secrets
Manager, attaches an App Runner instance role with GetSecretValue, and re-points
the service to secret ARNs (RuntimeEnvironmentSecrets). Idempotent.
"""
import json
import time
import boto3
from botocore.exceptions import ClientError

REGION = "us-west-2"
SERVICE = "artikbroker"
SECRET_KEYS = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "APP_SECRET",
               "INITIAL_ADMIN_PASSWORD", "APP_PASSWORD_HASH"]  # APP_PASSWORD_HASH = legacy/deprecated
INSTANCE_ROLE = "AppRunnerInstanceRole-artikbroker"

ar = boto3.client("apprunner", region_name=REGION)
sm = boto3.client("secretsmanager", region_name=REGION)
iam = boto3.client("iam")
acct = boto3.client("sts").get_caller_identity()["Account"]

# 1. Locate the service + read current config
svc = next(s for s in ar.list_services()["ServiceSummaryList"] if s["ServiceName"] == SERVICE)
desc = ar.describe_service(ServiceArn=svc["ServiceArn"])["Service"]
img_cfg = desc["SourceConfiguration"]["ImageRepository"]
cur_vars = img_cfg["ImageConfiguration"].get("RuntimeEnvironmentVariables", {})
access_role = desc["SourceConfiguration"]["AuthenticationConfiguration"]["AccessRoleArn"]
image_id = img_cfg["ImageIdentifier"]
inst = desc["InstanceConfiguration"]

# 2. Create/update one secret per key; collect ARNs
arns = {}
for k in SECRET_KEYS:
    val = cur_vars.get(k)
    if val is None:
        print(f"  ! {k} not in plaintext vars (maybe already migrated) — skipping create")
        continue
    name = f"{SERVICE}/{k}"
    try:
        r = sm.create_secret(Name=name, SecretString=val)
        arns[k] = r["ARN"]
        print(f"  created secret {name}")
    except sm.exceptions.ResourceExistsException:
        sm.put_secret_value(SecretId=name, SecretString=val)
        arns[k] = sm.describe_secret(SecretId=name)["ARN"]
        print(f"  updated secret {name}")

# If a key was already migrated, recover its ARN from Secrets Manager
for k in SECRET_KEYS:
    if k not in arns:
        arns[k] = sm.describe_secret(SecretId=f"{SERVICE}/{k}")["ARN"]

# 3. Instance role App Runner assumes to read the secrets
trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow",
        "Principal": {"Service": "tasks.apprunner.amazonaws.com"}, "Action": "sts:AssumeRole"}]}
policy = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow",
        "Action": "secretsmanager:GetSecretValue", "Resource": sorted(arns.values())}]}
try:
    iam.create_role(RoleName=INSTANCE_ROLE, AssumeRolePolicyDocument=json.dumps(trust))
    print(f"  created role {INSTANCE_ROLE}")
    time.sleep(10)
except iam.exceptions.EntityAlreadyExistsException:
    print(f"  role {INSTANCE_ROLE} exists")
iam.put_role_policy(RoleName=INSTANCE_ROLE, PolicyName="ReadArtikbrokerSecrets",
                    PolicyDocument=json.dumps(policy))
instance_role_arn = f"arn:aws:iam::{acct}:role/{INSTANCE_ROLE}"

# 4. Re-point the service: secrets by ARN, no plaintext, attach instance role
ar.update_service(
    ServiceArn=svc["ServiceArn"],
    SourceConfiguration={
        "AuthenticationConfiguration": {"AccessRoleArn": access_role},
        "AutoDeploymentsEnabled": False,
        "ImageRepository": {
            "ImageIdentifier": image_id,
            "ImageRepositoryType": "ECR",
            "ImageConfiguration": {
                "Port": "8080",
                "RuntimeEnvironmentVariables": {},          # plaintext cleared
                "RuntimeEnvironmentSecrets": arns,           # name -> secret ARN
            },
        },
    },
    InstanceConfiguration={
        "Cpu": inst.get("Cpu", "1024"),
        "Memory": inst.get("Memory", "2048"),
        "InstanceRoleArn": instance_role_arn,
    },
)
print("update-service submitted: 4 values now referenced from Secrets Manager, plaintext removed.")
