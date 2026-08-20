"""AppleBee's infrastructure, which is deliberately almost nothing.

One Lambda answers both the page and the API, reading the weather out of S3 in
byte ranges. There is no server, no database, no load balancer and no CDN in
this stack, because none of them is needed to answer a question that touches
18 KB of data. The bill at rest is the S3 storage: a few cents a month.

    pulumi up                                  # from infra/, or via CI

Two decisions are visible here and are the ones that keep it cheap:

* **A Function URL rather than API Gateway.** Free, and this is one origin.
* **A shared cache bucket.** A region run is 39 seconds of compute and the
  answer is deterministic, so the same request must never be paid for twice.
  Lambda's own /tmp dies with the container, which is why this is S3.

The one thing this stack does *not* create is the data. Weather and forage are
uploaded by ``scripts/upload_data.py``, because 1.7 GB does not belong in an
infrastructure diff.
"""

import json
import os

import pulumi
import pulumi_aws as aws

config = pulumi.Config()
name = config.get("name") or "applebee"
memory_mb = config.get_int("memoryMb") or 3008
timeout_seconds = config.get_int("timeoutSeconds") or 300
log_retention_days = config.get_int("logRetentionDays") or 14
# From the environment in CI, where it arrives as a GitHub secret, or from
# stack config when a human runs pulumi locally. Absent, approval of extension
# jobs is refused outright rather than left open.
admin_token = config.get_secret("adminToken") or os.environ.get("APPLEBEE_ADMIN_TOKEN")

account = aws.get_caller_identity()
suffix = account.account_id[-6:]

# ---------------------------------------------------------------------------
# Storage: the inputs, and the answers worth keeping
# ---------------------------------------------------------------------------

data = aws.s3.BucketV2(
    "data",
    bucket=f"{name}-data-{suffix}",
    tags={"Project": name, "Contents": "prism-weather-and-cdl-forage"},
)

# Private: PRISM's 4 km data is redistributable, but paying egress for anyone
# who wants 1.7 GB of it is a different question from being allowed to share it.
aws.s3.BucketPublicAccessBlock("data-private",
                               bucket=data.id,
                               block_public_acls=True, block_public_policy=True,
                               ignore_public_acls=True, restrict_public_buckets=True)

cache = aws.s3.BucketV2("cache", bucket=f"{name}-cache-{suffix}", tags={"Project": name})

aws.s3.BucketPublicAccessBlock("cache-private",
                               bucket=cache.id,
                               block_public_acls=True, block_public_policy=True,
                               ignore_public_acls=True, restrict_public_buckets=True)

# Cached region runs are reproducible from the parameters that name them, so
# they expire rather than accumulating a bill nobody is watching.
aws.s3.BucketLifecycleConfigurationV2(
    "cache-expiry",
    bucket=cache.id,
    rules=[aws.s3.BucketLifecycleConfigurationV2RuleArgs(
        id="expire-runs", status="Enabled",
        filter=aws.s3.BucketLifecycleConfigurationV2RuleFilterArgs(prefix="runs/"),
        expiration=aws.s3.BucketLifecycleConfigurationV2RuleExpirationArgs(days=90),
    )],
)

# ---------------------------------------------------------------------------
# The image, built outside this program
# ---------------------------------------------------------------------------

# Lambda rejects a manifest *list*, and buildx attaches provenance and SBOM
# attestations by default, which turn a single-platform build into exactly that:
#
#   InvalidParameterValueException: Source image ... is not valid
#
# pulumi-docker-build exposes no way to turn those off, so the image is built by
# buildx in CI with --provenance=false --sbom=false and this program is handed
# the result. The registry itself is a prerequisite, created by
# scripts/bootstrap_aws.py alongside the state bucket, because the image has to
# exist before the stack can refer to it.
image_uri = config.get("imageUri") or os.environ.get("APPLEBEE_IMAGE_URI")
if not image_uri:
    raise Exception(
        "no image: set APPLEBEE_IMAGE_URI, or pulumi config set imageUri. "
        "The deploy workflow builds and pushes it before running Pulumi."
    )

# ---------------------------------------------------------------------------
# The function
# ---------------------------------------------------------------------------

role = aws.iam.Role(
    "api-role",
    name=f"{name}-api-role",
    assume_role_policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Action": "sts:AssumeRole",
                       "Principal": {"Service": "lambda.amazonaws.com"}}],
    }),
)

aws.iam.RolePolicyAttachment(
    "api-logs", role=role.name,
    policy_arn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole")

aws.iam.RolePolicy(
    "api-data",
    role=role.id,
    policy=pulumi.Output.all(data.arn, cache.arn).apply(lambda arns: json.dumps({
        "Version": "2012-10-17",
        "Statement": [
            # Read-only on the inputs: the API answers questions about the data,
            # it never changes it. That is what the job queue is for.
            {"Effect": "Allow", "Action": ["s3:GetObject", "s3:ListBucket"],
             "Resource": [arns[0], f"{arns[0]}/*"]},
            {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject"],
             "Resource": f"{arns[1]}/runs/*"},
        ],
    })),
)

# Created here rather than left to Lambda, so retention is set from the first
# invocation. Logs kept forever are the quiet way a cheap stack stops being one.
logs = aws.cloudwatch.LogGroup("api-logs-group",
                               name=f"/aws/lambda/{name}-api",
                               retention_in_days=log_retention_days)

function = aws.lambda_.Function(
    "api",
    name=f"{name}-api",
    package_type="Image",
    image_uri=image_uri,
    role=role.arn,
    memory_size=memory_mb,
    timeout=timeout_seconds,
    architectures=["x86_64"],
    environment=aws.lambda_.FunctionEnvironmentArgs(variables={
        "APPLEBEE_REGIONS": "/var/task/regions.aws.json",
        "APPLEBEE_DATA_BUCKET": data.bucket,
        "APPLEBEE_CACHE_BUCKET": cache.bucket,
        **({"APPLEBEE_ADMIN_TOKEN": admin_token} if admin_token else {}),
    }),
    opts=pulumi.ResourceOptions(depends_on=[logs]),
)

url = aws.lambda_.FunctionUrl(
    "api-url",
    function_name=function.name,
    authorization_type="NONE",
    cors=aws.lambda_.FunctionUrlCorsArgs(
        allow_origins=["*"], allow_methods=["GET", "POST"],
        allow_headers=["content-type", "x-admin-token"], max_age=86400),
)

pulumi.export("url", url.function_url)
pulumi.export("data_bucket", data.bucket)
pulumi.export("cache_bucket", cache.bucket)
pulumi.export("image", image_uri)
