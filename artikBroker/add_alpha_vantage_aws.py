"""Add ALPHA_VANTAGE_API_KEY to AWS for artikBroker, the same way as the other
secrets: a Secrets Manager entry referenced by the App Runner service via the
instance role. The value is read from artikAgents/.env (never hardcoded here).
Idempotent.
"""
import json
from pathlib import Path
import boto3

REGION = "us-west-2"
KEY = "ALPHA_VANTAGE_API_KEY"
ALL_KEYS = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "APP_PASSWORD_HASH", "APP_SECRET", KEY]
ROLE = "AppRunnerInstanceRole-artikbroker"

# read the value from the gitignored .env (not hardcoded)
envf = Path(__file__).resolve().parent.parent / "artikAgents" / "agents" / ".env"
val = next((l.split("=", 1)[1].strip().strip('"').strip("'")
            for l in envf.read_text().splitlines() if l.startswith(f"{KEY}=")), None)
assert val, f"{KEY} not found in {envf}"

sm = boto3.client("secretsmanager", region_name=REGION)
iam = boto3.client("iam")
ar = boto3.client("apprunner", region_name=REGION)

name = f"artikbroker/{KEY}"
try:
    sm.create_secret(Name=name, SecretString=val)
    print(f"created secret {name}")
except sm.exceptions.ResourceExistsException:
    sm.put_secret_value(SecretId=name, SecretString=val)
    print(f"updated secret {name}")

# instance role policy must list every secret ARN
arns = {k: sm.describe_secret(SecretId=f"artikbroker/{k}")["ARN"] for k in ALL_KEYS}
iam.put_role_policy(RoleName=ROLE, PolicyName="ReadArtikbrokerSecrets",
                    PolicyDocument=json.dumps({"Version": "2012-10-17", "Statement": [{
                        "Effect": "Allow", "Action": "secretsmanager:GetSecretValue",
                        "Resource": sorted(arns.values())}]}))
print("instance role policy updated for", len(arns), "secrets")

# add the secret ref to the service (preserve image, roles, other secrets)
svc = next(s for s in ar.list_services()["ServiceSummaryList"] if s["ServiceName"] == "artikbroker")
d = ar.describe_service(ServiceArn=svc["ServiceArn"])["Service"]
sc, ic = d["SourceConfiguration"], d["InstanceConfiguration"]
ir = sc["ImageRepository"]
secs = ir["ImageConfiguration"].get("RuntimeEnvironmentSecrets", {})
secs[KEY] = arns[KEY]
ir["ImageConfiguration"]["RuntimeEnvironmentSecrets"] = secs
ar.update_service(
    ServiceArn=svc["ServiceArn"],
    SourceConfiguration={"AuthenticationConfiguration": sc["AuthenticationConfiguration"],
                         "AutoDeploymentsEnabled": sc.get("AutoDeploymentsEnabled", False),
                         "ImageRepository": ir},
    InstanceConfiguration={"Cpu": ic["Cpu"], "Memory": ic["Memory"], "InstanceRoleArn": ic["InstanceRoleArn"]},
)
print("service updated; secret refs now:", sorted(secs.keys()))
