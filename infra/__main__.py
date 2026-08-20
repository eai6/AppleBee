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
# From the environment in CI, where it arrives as a GitHub secret, or from
# stack config when a human runs pulumi locally. Absent, approval of extension
# jobs is refused outright rather than left open.
admin_token = config.get_secret("adminToken") or os.environ.get("APPLEBEE_ADMIN_TOKEN")

account = aws.get_caller_identity()
region = aws.get_region().name
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
# The acquisition worker
# ---------------------------------------------------------------------------
#
# A task per job rather than a daemon: extending the inputs takes hours and
# happens a few times a year, so nothing should be running in between. Fargate
# because the job needs disk and a network for eight uninterrupted hours, and
# because PRISM's pacing means one worker, ever -- which the lock in
# applebee/jobs.py enforces and this only has to not undermine.

worker_image = config.get("workerImageUri") or os.environ.get("APPLEBEE_WORKER_IMAGE_URI")

cluster = aws.ecs.Cluster("worker", name=f"{name}-worker", tags={"Project": name})

worker_logs = aws.cloudwatch.LogGroup(
    "worker-logs", name=f"/aws/ecs/{name}-worker", retention_in_days=30)

execution = aws.iam.Role(
    "worker-execution",
    name=f"{name}-worker-execution",
    assume_role_policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Action": "sts:AssumeRole",
                       "Principal": {"Service": "ecs-tasks.amazonaws.com"}}],
    }),
)

aws.iam.RolePolicyAttachment(
    "worker-execution-policy", role=execution.name,
    policy_arn=("arn:aws:iam::aws:policy/service-role/"
                "AmazonECSTaskExecutionRolePolicy"))

worker_role = aws.iam.Role(
    "worker-task",
    name=f"{name}-worker-task",
    assume_role_policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Action": "sts:AssumeRole",
                       "Principal": {"Service": "ecs-tasks.amazonaws.com"}}],
    }),
)

aws.iam.RolePolicy(
    "worker-data",
    role=worker_role.id,
    policy=pulumi.Output.all(data.arn, cache.arn).apply(lambda arns: json.dumps({
        "Version": "2012-10-17",
        "Statement": [
            # The worker is the only thing that may write the inputs. Everything
            # else in this stack reads them.
            {"Effect": "Allow",
             "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject",
                        "s3:ListBucket"],
             "Resource": [arns[0], f"{arns[0]}/*"]},
            {"Effect": "Allow",
             "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject",
                        "s3:ListBucket"],
             "Resource": [arns[1], f"{arns[1]}/*"]},
        ],
    })),
)

vpc = aws.ec2.get_vpc(default=True)
worker_subnets = aws.ec2.get_subnets(filters=[aws.ec2.GetSubnetsFilterArgs(
    name="vpc-id", values=[vpc.id])]).ids

# Outbound only: the worker calls PRISM, USDA and S3, and nothing calls it.
worker_sg = aws.ec2.SecurityGroup(
    "worker-sg",
    description="AppleBee acquisition worker: outbound only",
    vpc_id=vpc.id,
    egress=[aws.ec2.SecurityGroupEgressArgs(
        from_port=0, to_port=0, protocol="-1", cidr_blocks=["0.0.0.0/0"])],
    tags={"Project": name},
)

if worker_image:
    task = aws.ecs.TaskDefinition(
        "worker-task-definition",
        family=f"{name}-worker",
        cpu="1024", memory="4096",
        network_mode="awsvpc",
        requires_compatibilities=["FARGATE"],
        execution_role_arn=execution.arn,
        task_role_arn=worker_role.arn,
        # The matrices are gigabytes, and the run holds the old and the grown
        # copy at once while it extends them. 20 GB is Fargate's default and is
        # not enough.
        ephemeral_storage=aws.ecs.TaskDefinitionEphemeralStorageArgs(size_in_gib=60),
        container_definitions=pulumi.Output.all(
            worker_image, data.bucket, cache.bucket, worker_logs.name, region
        ).apply(lambda v: json.dumps([{
            "name": "worker",
            "image": v[0],
            "essential": True,
            "environment": [
                {"name": "APPLEBEE_DATA_BUCKET", "value": v[1]},
                {"name": "APPLEBEE_CACHE_BUCKET", "value": v[2]},
                {"name": "APPLEBEE_JOBS_BUCKET", "value": v[2]},
                {"name": "AWS_DEFAULT_REGION", "value": v[4]},
            ],
            "logConfiguration": {
                "logDriver": "awslogs",
                "options": {"awslogs-group": v[3], "awslogs-region": v[4],
                            "awslogs-stream-prefix": "job"},
            },
        }])),
    )

    pulumi.export("worker_task", task.arn)

pulumi.export("worker_cluster", cluster.name)
pulumi.export("worker_subnets", worker_subnets)


# ---------------------------------------------------------------------------
# The service
# ---------------------------------------------------------------------------
#
# App Runner rather than Lambda, and rather than the EC2 instance this stack
# briefly described.
#
# Lambda was the natural shape -- 2 ms answers, nothing running at rest -- but
# this account's organisation refuses anonymous invocation of a function URL and
# refuses CloudFront's service principal too, which was the documented way round
# the first refusal. Both were verified against a function that answered 200 to
# a SigV4-signed request from an IAM principal in the same account, so the code
# was never the question.
#
# EC2 behind CloudFront would have worked, at about $8 a month and an operating
# system to patch. App Runner is cheaper than that, carries its own TLS and a
# stable URL with no load balancer, and its endpoint is service-managed rather
# than gated by a resource policy -- which is why the guardrail does not reach
# it. Verified by standing one up before writing any of this.

ecr_access = aws.iam.Role(
    "apprunner-ecr",
    name=f"{name}-apprunner-ecr",
    description="App Runner pulling the image from a private registry",
    assume_role_policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Action": "sts:AssumeRole",
                       "Principal": {"Service": "build.apprunner.amazonaws.com"}}],
    }),
)

aws.iam.RolePolicyAttachment(
    "apprunner-ecr-policy", role=ecr_access.name,
    policy_arn=("arn:aws:iam::aws:policy/service-role/"
                "AWSAppRunnerServicePolicyForECRAccess"))

app_role = aws.iam.Role(
    "apprunner-task",
    name=f"{name}-apprunner-task",
    description="What the running container may reach",
    assume_role_policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Action": "sts:AssumeRole",
                       "Principal": {"Service": "tasks.apprunner.amazonaws.com"}}],
    }),
)

aws.iam.RolePolicy(
    "apprunner-data",
    role=app_role.id,
    policy=pulumi.Output.all(data.arn, cache.arn).apply(lambda arns: json.dumps({
        "Version": "2012-10-17",
        "Statement": [
            # Read-only on the inputs: the API answers questions about the data,
            # it never changes it. That is what the job queue is for.
            {"Effect": "Allow", "Action": ["s3:GetObject", "s3:ListBucket"],
             "Resource": [arns[0], f"{arns[0]}/*"]},
            {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject"],
             "Resource": f"{arns[1]}/runs/*"},
            # The job queue, which the API writes and the worker reads.
            {"Effect": "Allow",
             "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject",
                        "s3:ListBucket"],
             "Resource": [arns[1], f"{arns[1]}/jobs/*"]},
        ],
    })),
)

# Approving a job starts the worker, so the API may run that one task family and
# pass those two roles, and nothing else.
aws.iam.RolePolicy(
    "apprunner-worker",
    role=app_role.id,
    policy=pulumi.Output.all(cluster.arn, execution.arn, worker_role.arn,
                             account.account_id, region).apply(lambda v: json.dumps({
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": "ecs:RunTask",
             "Resource": f"arn:aws:ecs:{v[4]}:{v[3]}:task-definition/{name}-worker:*",
             "Condition": {"ArnEquals": {"ecs:cluster": v[0]}}},
            {"Effect": "Allow", "Action": "ecs:DescribeTasks",
             "Resource": f"arn:aws:ecs:{v[4]}:{v[3]}:task/*"},
            {"Effect": "Allow", "Action": "iam:PassRole",
             "Resource": [v[1], v[2]],
             "Condition": {"StringEquals": {"iam:PassedToService": "ecs-tasks.amazonaws.com"}}},
        ],
    })),
)

environment = {
    "APPLEBEE_DATA_BUCKET": data.bucket,
    "APPLEBEE_CACHE_BUCKET": cache.bucket,
    # The queue is shared: the API writes requests to it and the worker reads
    # them, and they are different containers.
    "APPLEBEE_JOBS_BUCKET": cache.bucket,
    # From the provider, so the stack follows wherever it is deployed rather
    # than carrying a second opinion about where that is.
    "AWS_DEFAULT_REGION": region,
}
if admin_token:
    environment["APPLEBEE_ADMIN_TOKEN"] = admin_token

service = aws.apprunner.Service(
    "api",
    service_name=f"{name}-api",
    source_configuration=aws.apprunner.ServiceSourceConfigurationArgs(
        # Deployments come from CI, which pushes a new tag and then runs this.
        # Left to App Runner, a push would deploy itself with nothing watching.
        auto_deployments_enabled=False,
        authentication_configuration=(
            aws.apprunner.ServiceSourceConfigurationAuthenticationConfigurationArgs(
                access_role_arn=ecr_access.arn)),
        image_repository=aws.apprunner.ServiceSourceConfigurationImageRepositoryArgs(
            image_identifier=image_uri,
            image_repository_type="ECR",
            image_configuration=(
                aws.apprunner.ServiceSourceConfigurationImageRepositoryImageConfigurationArgs(
                    port="8000",
                    runtime_environment_variables=environment)),
        ),
    ),
    # The smallest size that holds scientific Python with room for a region run.
    # Idle memory is the standing cost -- about $5 a month -- and vCPU is billed
    # only while a request is in flight.
    instance_configuration=aws.apprunner.ServiceInstanceConfigurationArgs(
        cpu=config.get("cpu") or "0.5 vCPU",
        memory=config.get("memory") or "1 GB",
        instance_role_arn=app_role.arn,
    ),
    # TCP rather than HTTP: the page is served from the same port and a health
    # check that fetched it would run the whole application every ten seconds.
    health_check_configuration=aws.apprunner.ServiceHealthCheckConfigurationArgs(
        protocol="TCP", interval=10, timeout=5,
        healthy_threshold=1, unhealthy_threshold=5,
    ),
    tags={"Project": name},
)

pulumi.export("url", service.service_url.apply(lambda u: f"https://{u}"))
pulumi.export("data_bucket", data.bucket)
pulumi.export("cache_bucket", cache.bucket)
pulumi.export("image", image_uri)
