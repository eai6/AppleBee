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
instance_type = config.get("instanceType") or "t3.micro"
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
# The server
# ---------------------------------------------------------------------------
#
# Not a Lambda. The account's organisation forbids anonymous invocation of a
# function URL *and* refuses CloudFront's service principal, which was the
# documented way round the first block -- both verified against a function that
# answered 200 to a SigV4-signed request from an IAM principal in the account.
# An ordinary HTTP server behind CloudFront involves no invoke permission at
# all, so no guardrail applies to it.
#
# The trade is honest: about $8 a month against the $0.50 the serverless shape
# would have cost, and an instance that has to be patched.

role = aws.iam.Role(
    "api-role",
    name=f"{name}-api-role",
    assume_role_policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Action": "sts:AssumeRole",
                       "Principal": {"Service": "ec2.amazonaws.com"}}],
    }),
)

aws.iam.RolePolicyAttachment(
    "api-ecr", role=role.name,
    policy_arn="arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role")

# Session Manager, so the instance needs no SSH key and no open port 22.
aws.iam.RolePolicyAttachment(
    "api-ssm", role=role.name,
    policy_arn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore")

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

profile = aws.iam.InstanceProfile("api-profile", name=f"{name}-api", role=role.name)

vpc = aws.ec2.get_vpc(default=True)
subnets = aws.ec2.get_subnets(filters=[aws.ec2.GetSubnetsFilterArgs(
    name="vpc-id", values=[vpc.id])])

# Only CloudFront may reach the origin. AWS publishes the edge ranges as a
# managed prefix list, so this is narrower than "the internet" and does not
# drift as those ranges change.
edges = aws.ec2.get_managed_prefix_list(name="com.amazonaws.global.cloudfront.origin-facing")

security = aws.ec2.SecurityGroup(
    "api-sg",
    description="AppleBee origin: CloudFront in, anywhere out",
    vpc_id=vpc.id,
    ingress=[aws.ec2.SecurityGroupIngressArgs(
        description="CloudFront edge locations",
        from_port=80, to_port=80, protocol="tcp", prefix_list_ids=[edges.id])],
    egress=[aws.ec2.SecurityGroupEgressArgs(
        from_port=0, to_port=0, protocol="-1", cidr_blocks=["0.0.0.0/0"])],
    tags={"Project": name},
)

ami = aws.ec2.get_ami(
    most_recent=True, owners=["amazon"],
    filters=[aws.ec2.GetAmiFilterArgs(name="name", values=["al2023-ami-*-x86_64"])],
)

# 1 GB of memory with scientific Python loaded is workable but not roomy, and a
# region run is the one moment it matters, so the instance gets swap rather than
# the next size up at twice the price.
startup = pulumi.Output.all(image_uri, data.bucket, cache.bucket).apply(
    lambda values: f"""#!/bin/bash
set -euxo pipefail
dnf install -y docker
systemctl enable --now docker

fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin {values[0].split('/')[0]}

docker run -d --name applebee --restart always -p 80:8000 \
  -e APPLEBEE_DATA_BUCKET={values[1]} \
  -e APPLEBEE_CACHE_BUCKET={values[2]} \
  -e AWS_DEFAULT_REGION=us-east-1 \
  {values[0]}
""")

server = aws.ec2.Instance(
    "api",
    instance_type=instance_type,
    ami=ami.id,
    subnet_id=subnets.ids[0],
    vpc_security_group_ids=[security.id],
    iam_instance_profile=profile.name,
    associate_public_ip_address=True,
    user_data=startup,
    # Replace the instance when the image changes: the container is baked into
    # the startup script, so a new image means a new machine rather than a
    # machine quietly running last week's code.
    user_data_replace_on_change=True,
    root_block_device=aws.ec2.InstanceRootBlockDeviceArgs(
        volume_size=12, volume_type="gp3", delete_on_termination=True),
    tags={"Name": f"{name}-api", "Project": name},
)

# A fixed address, so CloudFront's origin survives a stop or a replacement.
address = aws.ec2.Eip("api-ip", instance=server.id, domain="vpc",
                      tags={"Project": name})

# ---------------------------------------------------------------------------
# The edge
# ---------------------------------------------------------------------------

CACHING_DISABLED = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
ALL_VIEWER = "216adef6-5c7f-47e4-b989-5492eafa07d3"

distribution = aws.cloudfront.Distribution(
    "api-cdn",
    enabled=True,
    comment=f"{name}: the model, its evaluations and its map",
    origins=[aws.cloudfront.DistributionOriginArgs(
        origin_id="server",
        domain_name=address.public_dns,
        custom_origin_config=aws.cloudfront.DistributionOriginCustomOriginConfigArgs(
            http_port=80, https_port=443,
            # The hop to the origin is HTTP because the origin is an IP address
            # with no certificate; viewers are redirected to HTTPS and CloudFront
            # terminates TLS.
            origin_protocol_policy="http-only",
            origin_ssl_protocols=["TLSv1.2"],
            origin_read_timeout=60,
        ),
    )],
    default_cache_behavior=aws.cloudfront.DistributionDefaultCacheBehaviorArgs(
        target_origin_id="server",
        viewer_protocol_policy="redirect-to-https",
        allowed_methods=["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"],
        cached_methods=["GET", "HEAD"],
        # Answers are already cached in S3 by parameter hash, and a region run
        # exceeds what the edge would hold anyway.
        cache_policy_id=CACHING_DISABLED,
        origin_request_policy_id=ALL_VIEWER,
        compress=True,
    ),
    restrictions=aws.cloudfront.DistributionRestrictionsArgs(
        geo_restriction=aws.cloudfront.DistributionRestrictionsGeoRestrictionArgs(
            restriction_type="none"),
    ),
    viewer_certificate=aws.cloudfront.DistributionViewerCertificateArgs(
        cloudfront_default_certificate=True),
    price_class="PriceClass_100",     # North America and Europe; the audience
)

pulumi.export("url", distribution.domain_name.apply(lambda d: f"https://{d}"))
pulumi.export("origin", address.public_dns)
pulumi.export("data_bucket", data.bucket)
pulumi.export("cache_bucket", cache.bucket)
pulumi.export("image", image_uri)
