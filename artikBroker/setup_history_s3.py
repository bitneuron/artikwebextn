"""Provision the S3-backed search-history store for artikBroker on AWS. Idempotent.

Does three things:
  1. Create a private, encrypted S3 bucket (public access fully blocked).
  2. Grant the App Runner *instance* role read/write on that bucket (a separate
     inline policy, so the existing secrets policy is untouched).
  3. Set HISTORY_S3_BUCKET as a runtime ENV VAR on the service (preserving the
     image, secrets, roles and any other env vars). The app switches to S3
     automatically when that var is present.

Run with the artikAPIs venv python (has boto3):
    ../artikAPIs/venv/bin/python setup_history_s3.py
Then ship the code (boto3 + history endpoints) with ./redeploy.sh.
"""
import json
import boto3

REGION = "us-west-2"
ACCOUNT = "515966528039"
BUCKET = f"artikbroker-search-history-{ACCOUNT}"
ROLE = "AppRunnerInstanceRole-artikbroker"
ENV_KEY = "HISTORY_S3_BUCKET"

s3 = boto3.client("s3", region_name=REGION)
iam = boto3.client("iam")
ar = boto3.client("apprunner", region_name=REGION)

# 1) bucket (private + encrypted) ------------------------------------------------
try:
    s3.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})
    print(f"created bucket {BUCKET}")
except s3.exceptions.BucketAlreadyOwnedByYou:
    print(f"bucket {BUCKET} already exists")

s3.put_public_access_block(
    Bucket=BUCKET,
    PublicAccessBlockConfiguration={
        "BlockPublicAcls": True, "IgnorePublicAcls": True,
        "BlockPublicPolicy": True, "RestrictPublicBuckets": True,
    },
)
s3.put_bucket_encryption(
    Bucket=BUCKET,
    ServerSideEncryptionConfiguration={
        "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
    },
)
print("public access blocked + default encryption on")

# 2) instance-role policy (separate from the secrets policy) ---------------------
iam.put_role_policy(
    RoleName=ROLE, PolicyName="ReadWriteHistoryBucket",
    PolicyDocument=json.dumps({
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": ["s3:ListBucket"],
             "Resource": f"arn:aws:s3:::{BUCKET}"},
            {"Effect": "Allow",
             "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
             "Resource": f"arn:aws:s3:::{BUCKET}/*"},
        ],
    }),
)
print(f"instance role {ROLE} granted read/write on {BUCKET}")

# 3) set the env var on the service (preserve image/secrets/roles/other vars) ----
svc = next(s for s in ar.list_services()["ServiceSummaryList"] if s["ServiceName"] == "artikbroker")
d = ar.describe_service(ServiceArn=svc["ServiceArn"])["Service"]
sc, ic = d["SourceConfiguration"], d["InstanceConfiguration"]
ir = sc["ImageRepository"]
cfg = ir["ImageConfiguration"]
envs = cfg.get("RuntimeEnvironmentVariables", {})
if envs.get(ENV_KEY) == BUCKET:
    print(f"service already has {ENV_KEY}={BUCKET}; nothing to update")
else:
    envs[ENV_KEY] = BUCKET
    cfg["RuntimeEnvironmentVariables"] = envs
    ar.update_service(
        ServiceArn=svc["ServiceArn"],
        SourceConfiguration={
            "AuthenticationConfiguration": sc["AuthenticationConfiguration"],
            "AutoDeploymentsEnabled": sc.get("AutoDeploymentsEnabled", False),
            "ImageRepository": ir,
        },
        InstanceConfiguration={"Cpu": ic["Cpu"], "Memory": ic["Memory"],
                               "InstanceRoleArn": ic["InstanceRoleArn"]},
    )
    print(f"service updated: {ENV_KEY}={BUCKET}")

print("\nDone. Now run ./redeploy.sh to ship the history code (boto3 + endpoints).")
