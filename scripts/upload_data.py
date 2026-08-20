"""Put the model's inputs where the deployed API can read them.

Not part of the Pulumi stack: 1.7 GB does not belong in an infrastructure diff,
and the data changes on a completely different schedule from the code. This is
run once after the first deploy, and again whenever an extension job adds years.

    python scripts/upload_data.py --bucket applebee-data-123456 --dry-run
    python scripts/upload_data.py --bucket applebee-data-123456 --profile ecomorph

Only what the API actually reads is uploaded. The CONUS matrices stay on disk:
the platform serves the Northeast, which is the extent the model was evaluated
in, and 7.9 GB of unused weather would be 7.9 GB of bill.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from applebee.config import INPUTS  # noqa: E402

# (local path, key prefix). Weather is uploaded per region rather than wholesale
# so that adding CONUS later is a deliberate act rather than a default.
UPLOADS = [
    (INPUTS / "weather" / "northeast", "weather/northeast"),
    (INPUTS / "weather" / "pennsylvania", "weather/pennsylvania"),
    (INPUTS / "forage" / "northeast_forage_spring_lonsdorf.csv",
     "forage/northeast_forage_spring_lonsdorf.csv"),
    (INPUTS / "forage" / "pa_forage_spring_lonsdorf.csv",
     "forage/pa_forage_spring_lonsdorf.csv"),
    (INPUTS / "observations", "observations"),
]


def size_of(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--profile", default="ecomorph")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    total, plan = 0, []
    for source, key in UPLOADS:
        if not source.exists():
            print(f"  absent, skipping: {source}")
            continue
        size = size_of(source)
        total += size
        verb = "cp" if source.is_file() else "sync"
        plan.append(["aws", "s3", verb, str(source), f"s3://{args.bucket}/{key}",
                     "--profile", args.profile,
                     *(["--size-only"] if verb == "sync" else [])])
        print(f"  {size / 1e6:>9,.1f} MB  {key}")

    print(f"\n  {total / 1e9:.2f} GB total "
          f"— about ${total / 1e9 * 0.023:.2f}/month in S3 Standard")
    if args.dry_run:
        print("\ndry run. Commands that would run:")
        for command in plan:
            print("  " + " ".join(command))
        return

    for command in plan:
        print(f"\n$ {' '.join(command)}")
        if subprocess.run(command).returncode != 0:
            raise SystemExit("upload failed")
    print("\nDone.")


if __name__ == "__main__":
    main()
