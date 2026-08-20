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
    parser.add_argument("--environment", default="production",
                        help="GitHub environment the deploy job declares")
    parser.add_argument("--owner-id", type=int, default=None,
                        help="numeric owner id; read from GitHub when omitted")
    parser.add_argument("--repo-id", type=int, default=None,
                        help="numeric repository id; read from GitHub when omitted")
    parser.add_argument("--name", default="applebee")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.owner_id is None or args.repo_id is None:
        ids = subprocess.run(["gh", "api", f"repos/{args.repo}",
                              "--jq", "{owner: .owner.id, repo: .id}"],
                             capture_output=True, text=True)
        if ids.returncode == 0:
            found = json.loads(ids.stdout)
            args.owner_id = args.owner_id or found["owner"]
            args.repo_id = args.repo_id or found["repo"]
        else:
            print("  could not read the repository ids from GitHub; pass "
                  "--owner-id and --repo-id, or the immutable subject will not "
                  "be trusted")

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
    # GitHub now issues an *immutable* subject carrying the numeric owner and
    # repository IDs -- `repo:owner@1234/name@5678:...` -- so that renaming a
    # repository cannot inherit another one's trust. Every tutorial still shows
    # the older `repo:owner/name:...` form, and a policy written that way fails
    # with "Not authorized to perform sts:AssumeRoleWithWebIdentity" naming
    # neither the claim nor the value. Both forms are trusted here: the current
    # one because it is what arrives, the older one so this keeps working if
    # GitHub reverts.
    #
    # A job that declares `environment:` gets an environment subject rather than
    # a branch one, so both of those are covered too.
    owner, _, repository = args.repo.partition("/")
    identified = (f"{owner}@{args.owner_id}/{repository}@{args.repo_id}"
                  if args.owner_id and args.repo_id else None)
    subjects = [f"repo:{args.repo}:ref:refs/heads/{args.branch}",
                f"repo:{args.repo}:environment:{args.environment}"]
    if identified:
        subjects += [f"repo:{identified}:ref:refs/heads/{args.branch}",
                     f"repo:{identified}:environment:{args.environment}"]

    print(f"account      : {account}")
    print(f"region       : {args.region}")
    for subject in subjects:
        print(f"trusts       : {subject}")
    print(f"role         : {role_name}")
    print(f"state bucket : {state_bucket}")
    print(f"registry     : {args.name}-api\n")
    if args.dry_run:
        print("dry run: nothing created.")
        return

    # 1. The OIDC provider.
    code, existing = aws(args.profile, "iam", "get-open-id-connect-provider",
                         "--open-id-connect-provider-arn", provider_arn, check=False)
    if code == 0:
        audiences = json.loads(existing)["ClientIDList"]
        if "sts.amazonaws.com" not in audiences:
            aws(args.profile, "iam", "add-client-id-to-open-id-connect-provider",
                "--open-id-connect-provider-arn", provider_arn,
                "--client-id", "sts.amazonaws.com")
            print("  OIDC provider present; added the sts.amazonaws.com audience")
        else:
            print("  OIDC provider already present, with the right audience")
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
                "StringEquals": {f"{GITHUB_ISSUER}:aud": "sts.amazonaws.com"},
                "StringLike": {f"{GITHUB_ISSUER}:sub": subjects},
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

    # 4. The container registry. A prerequisite rather than part of the stack:
    #    CI builds and pushes the image before Pulumi runs, because Lambda needs
    #    an image without buildx's default attestations and the stack cannot
    #    produce one.
    repository = f"{args.name}-api"
    if exists(args.profile, "ecr", "describe-repositories",
              "--repository-names", repository):
        print("  ECR repository already present")
    else:
        aws(args.profile, "ecr", "create-repository", "--repository-name", repository,
            "--image-scanning-configuration", "scanOnPush=true")
        print("  ECR repository created")
    aws(args.profile, "ecr", "put-lifecycle-policy", "--repository-name", repository,
        "--lifecycle-policy-text", json.dumps({"rules": [{
            "rulePriority": 1,
            "description": "keep the last 5 images",
            "selection": {"tagStatus": "any", "countType": "imageCountMoreThan",
                          "countNumber": 5},
            "action": {"type": "expire"},
        }]}))

    print("\nDone. Set these as GitHub repository secrets:\n")
    print(f"  AWS_DEPLOY_ROLE_ARN   arn:aws:iam::{account}:role/{role_name}")
    print(f"  PULUMI_STATE_BUCKET   {state_bucket}")
    print("  PULUMI_CONFIG_PASSPHRASE   (any strong passphrase you choose)")
    print("\n  gh secret set AWS_DEPLOY_ROLE_ARN --body "
          f"arn:aws:iam::{account}:role/{role_name}")


if __name__ == "__main__":
    sys.exit(main())
