"""Create the one-time AWS pieces that CI cannot create for itself.

Everything else is Pulumi's job. These three are not, because they are what lets
Pulumi run at all from GitHub Actions without a long-lived access key:

1. an OIDC provider trusting GitHub's token issuer,
2. a role that only this repository, on its default branch, may assume,
3. an S3 bucket holding Pulumi's state.

Run once, by a human with credentials:

    python scripts/bootstrap_aws.py --profile ecomorph --dry-run
    python scripts/bootstrap_aws.py --profile ecomorph

It is idempotent: anything already there is reported and left alone.

The role is not an administrator. It gets PowerUserAccess, which excludes IAM,
plus a narrow policy for managing roles whose names begin with the project's --
so a compromised workflow can create the stack's own execution role and nothing
that would let it escalate.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

GITHUB_ISSUER = "token.actions.githubusercontent.com"
THUMBPRINT = "6938fd4d98bab03faadb97b34396831e3780aea1"


def aws(profile: str, *args: str, check: bool = True) -> tuple[int, str]:
    command = ["aws", *args, "--profile", profile, "--output", "json"]
    done = subprocess.run(command, capture_output=True, text=True)
    if check and done.returncode != 0:
        raise SystemExit(f"failed: {' '.join(command)}\n{done.stderr.strip()}")
    return done.returncode, done.stdout.strip()


def exists(profile: str, *args: str) -> bool:
    return aws(profile, *args, check=False)[0] == 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", default="ecomorph")
    parser.add_argument("--repo", default="eai6/AppleBee")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--name", default="applebee")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    code, identity = aws(args.profile, "sts", "get-caller-identity", check=False)
    if code != 0:
        raise SystemExit(
            f"no usable credentials for profile {args.profile!r}.\n"
            f"Authenticate first:  aws login --profile {args.profile}"
        )
    account = json.loads(identity)["Account"]
    provider_arn = f"arn:aws:iam::{account}:oidc-provider/{GITHUB_ISSUER}"
    role_name = f"{args.name}-github-deploy"
    state_bucket = f"{args.name}-pulumi-state-{account[-6:]}"
    subject = f"repo:{args.repo}:ref:refs/heads/{args.branch}"

    print(f"account      : {account}")
    print(f"region       : {args.region}")
    print(f"trusts       : {subject}")
    print(f"role         : {role_name}")
    print(f"state bucket : {state_bucket}\n")
    if args.dry_run:
        print("dry run: nothing created.")
        return

    # 1. The OIDC provider.
    if exists(args.profile, "iam", "get-open-id-connect-provider",
              "--open-id-connect-provider-arn", provider_arn):
        print("  OIDC provider already present")
    else:
        aws(args.profile, "iam", "create-open-id-connect-provider",
            "--url", f"https://{GITHUB_ISSUER}",
            "--client-id-list", "sts.amazonaws.com",
            "--thumbprint-list", THUMBPRINT)
        print("  OIDC provider created")

    # 2. The role, trusted by this repository and branch only.
    trust = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Federated": provider_arn},
            "Action": "sts:AssumeRoleWithWebIdentity",
            "Condition": {
                "StringEquals": {f"{GITHUB_ISSUER}:aud": "sts.amazonaws.com",
                                 f"{GITHUB_ISSUER}:sub": subject},
            },
        }],
    }
    if exists(args.profile, "iam", "get-role", "--role-name", role_name):
        aws(args.profile, "iam", "update-assume-role-policy", "--role-name", role_name,
            "--policy-document", json.dumps(trust))
        print("  role already present; trust policy refreshed")
    else:
        aws(args.profile, "iam", "create-role", "--role-name", role_name,
            "--assume-role-policy-document", json.dumps(trust),
            "--description", f"GitHub Actions deploys for {args.repo}")
        print("  role created")

    aws(args.profile, "iam", "attach-role-policy", "--role-name", role_name,
        "--policy-arn", "arn:aws:iam::aws:policy/PowerUserAccess")

    # PowerUserAccess deliberately excludes IAM, so the stack could not create
    # its own Lambda execution role. This adds exactly that, and only for roles
    # carrying the project's name.
    aws(args.profile, "iam", "put-role-policy", "--role-name", role_name,
        "--policy-name", "manage-project-roles",
        "--policy-document", json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": ["iam:CreateRole", "iam:DeleteRole", "iam:GetRole",
                           "iam:PassRole", "iam:TagRole", "iam:ListRolePolicies",
                           "iam:AttachRolePolicy", "iam:DetachRolePolicy",
                           "iam:PutRolePolicy", "iam:DeleteRolePolicy",
                           "iam:GetRolePolicy", "iam:ListAttachedRolePolicies"],
                "Resource": f"arn:aws:iam::{account}:role/{args.name}-*",
            }],
        }))
    print("  policies attached")

    # 3. Pulumi's state, versioned so a bad deploy can be walked back.
    if exists(args.profile, "s3api", "head-bucket", "--bucket", state_bucket):
        print("  state bucket already present")
    else:
        create = ["s3api", "create-bucket", "--bucket", state_bucket,
                  "--region", args.region]
        if args.region != "us-east-1":
            create += ["--create-bucket-configuration",
                       f"LocationConstraint={args.region}"]
        aws(args.profile, *create)
        aws(args.profile, "s3api", "put-bucket-versioning", "--bucket", state_bucket,
            "--versioning-configuration", "Status=Enabled")
        aws(args.profile, "s3api", "put-public-access-block", "--bucket", state_bucket,
            "--public-access-block-configuration",
            "BlockPublicAcls=true,IgnorePublicAcls=true,"
            "BlockPublicPolicy=true,RestrictPublicBuckets=true")
        print("  state bucket created")

    print("\nDone. Set these as GitHub repository secrets:\n")
    print(f"  AWS_DEPLOY_ROLE_ARN   arn:aws:iam::{account}:role/{role_name}")
    print(f"  PULUMI_STATE_BUCKET   {state_bucket}")
    print("  PULUMI_CONFIG_PASSPHRASE   (any strong passphrase you choose)")
    print("\n  gh secret set AWS_DEPLOY_ROLE_ARN --body "
          f"arn:aws:iam::{account}:role/{role_name}")


if __name__ == "__main__":
    sys.exit(main())
