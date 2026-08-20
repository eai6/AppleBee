"""Carry out one approved extension job, then stop.

This is what runs on Fargate when an administrator approves a request. It takes
one job, does it, records what happened, and exits — a task per job rather than
a daemon, because the work is measured in hours and happens a few times a year.

    python scripts/run_worker.py                 # claim and run one job
    python scripts/run_worker.py --job abc123    # run a specific approved job
    python scripts/run_worker.py --dry-run       # say what would happen

The fetching itself is `scripts/fetch_prism.py` and `scripts/build_forage.py`,
run as subprocesses. They are paced, resumable and proven; this adds only the
three things a container needs that a laptop does not — bringing the inputs down
from S3 first, putting the results back afterwards, and holding the lock
throughout so that two workers can never fetch at once.

**The matrices are extended, not rebuilt.** `fetch_and_sample` sizes its array
to the range it is asked for and discards a cache of a different shape, so
asking for 2013-2025 on top of a 2013-2018 cache would re-fetch six years that
are already held — twelve hours of PRISM's pacing, for nothing.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from applebee import jobs  # noqa: E402
from applebee.acquire import prism  # noqa: E402
from applebee.config import DATA, INPUTS  # noqa: E402

HEARTBEAT_SECONDS = 300


def s3():
    import boto3

    return boto3.client("s3")


def pull(bucket: str, prefix: str, into: Path) -> int:
    """Everything under a prefix, onto local disk. Returns the file count."""
    into.mkdir(parents=True, exist_ok=True)
    pages = s3().get_paginator("list_objects_v2")
    count = 0
    for page in pages.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            target = into / obj["Key"][len(prefix):].lstrip("/")
            target.parent.mkdir(parents=True, exist_ok=True)
            s3().download_file(bucket, obj["Key"], str(target))
            count += 1
    return count


def push(source: Path, bucket: str, prefix: str) -> int:
    """A directory, or a single file, back into the bucket."""
    files = [source] if source.is_file() else [p for p in source.rglob("*") if p.is_file()]
    for path in files:
        key = prefix if source.is_file() else f"{prefix}/{path.relative_to(source)}"
        s3().upload_file(str(path), bucket, key)
    return len(files)


def beat(store: jobs.JobStore, stop: threading.Event) -> None:
    """Say the worker is alive, so an eight-hour fetch is not called abandoned."""
    while not stop.wait(HEARTBEAT_SECONDS):
        try:
            store.heartbeat()
        except Exception as exc:  # noqa: BLE001 -- a missed beat must not end the job
            print(f"  heartbeat failed: {exc}", flush=True)


def run(command: list[str]) -> None:
    print(f"\n$ {' '.join(command)}\n", flush=True)
    done = subprocess.run(command, cwd=Path(__file__).resolve().parent.parent)
    if done.returncode != 0:
        raise RuntimeError(f"{command[1]} exited {done.returncode}")


def do_weather(job: jobs.Job, bucket: str, dry_run: bool) -> str:
    region = job.parameters["region"]
    start, end = job.parameters["start"], job.parameters["end"]
    local = INPUTS / "weather" / region

    if dry_run:
        return f"would extend {region} to {start}..{end} and fetch the missing days"

    held = pull(bucket, f"weather/{region}", local)
    print(f"  {held} file(s) of existing weather brought down", flush=True)

    for variable in ("tmean", "ppt"):
        key = f"{region}_{variable}" if region != "pennsylvania" else f"pa_{variable}"
        print(f"  {key}: {prism.extend_matrix(local, key, start, end)}", flush=True)

    run([sys.executable, "scripts/fetch_prism.py", "--region", region,
         "--start", start, "--end", end, "--discard-rasters"])

    sent = push(local, bucket, f"weather/{region}")
    return f"fetched {start}..{end} and returned {sent} file(s) to S3"


def do_forage(job: jobs.Job, bucket: str, dry_run: bool) -> str:
    region = job.parameters["region"]
    years = sorted(int(y) for y in job.parameters["years"])
    partials = INPUTS / "forage" / f"{region}_forage_by_year"

    if dry_run:
        return f"would build the {region} forage index for {years[0]}..{years[-1]}"

    held = pull(bucket, f"forage/{region}_forage_by_year", partials)
    print(f"  {held} year(s) already computed", flush=True)

    # Every year is asked for, not only the new ones: the combined table is
    # rewritten from the partials, and a year already computed is reused rather
    # than re-downloaded.
    run([sys.executable, "scripts/build_forage.py", "--region", region,
         "--years", str(years[0]), str(years[-1]), "--discard-rasters"])

    combined = INPUTS / "forage" / f"{region}_forage_spring_lonsdorf.csv"
    push(partials, bucket, f"forage/{region}_forage_by_year")
    push(combined, bucket, f"forage/{combined.name}")
    return f"built {years[0]}..{years[-1]} and returned the index to S3"


HANDLERS = {"weather": do_weather, "forage": do_forage}


def main() -> None:
    import os

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--job", help="a specific approved job; the oldest otherwise")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    bucket = os.environ.get("APPLEBEE_DATA_BUCKET")
    if not bucket and not args.dry_run:
        raise SystemExit("APPLEBEE_DATA_BUCKET is not set; the worker has nowhere to read")

    store = jobs.JobStore()
    job = store.claim() if not args.job else store.get(args.job)
    if job is None:
        print("nothing approved to run.")
        return
    if args.job and job.state != jobs.RUNNING:
        job = store._transition(job.id, jobs.RUNNING, {jobs.APPROVED}, by="worker")

    print(f"job {job.id}: {job.kind} {job.parameters}", flush=True)
    started = time.time()
    stop = threading.Event()
    threading.Thread(target=beat, args=(store, stop), daemon=True).start()

    try:
        note = HANDLERS[job.kind](job, bucket, args.dry_run)
    except Exception as exc:  # noqa: BLE001 -- recorded on the job, not just logged
        stop.set()
        store.finish(job.id, False, note=f"{type(exc).__name__}: {exc}")
        raise
    stop.set()
    elapsed = (time.time() - started) / 3600
    store.finish(job.id, True, note=f"{note} in {elapsed:.1f} h")
    print(f"\ndone in {elapsed:.2f} h: {note}", flush=True)


if __name__ == "__main__":
    main()
