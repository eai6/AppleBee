"""Extension jobs — the only route by which the input data ever changes.

PRISM's download service allows two fetches of a file per 24 hours and blocks
IPs that crowd it, and a block would take the platform's whole data supply with
it. So extension is not something a visitor does. A visitor **requests** it, an
administrator approves it, and exactly one worker at a time carries it out
behind a lock.

The jobs themselves are described here and executed by the scripts that already
do the work -- ``scripts/fetch_prism.py`` and ``scripts/build_forage.py`` --
rather than by a second copy of the fetching logic. Those scripts are paced,
resumable and proven; a job is a durable record of an intention to run one.

    store = JobStore()
    job = store.request("weather", region="northeast", start="2019-01-01",
                        end="2025-12-31", requested_by="a.grower@example.com")
    store.plan(job.id)              # what it would cost; no network
    store.approve(job.id)           # an administrator, not a visitor
    store.claim()                   # the worker, one at a time

State lives in one JSON file per job, which is enough for a single worker and
maps directly onto the object store the deployment will use. The lock is a file
created exclusively, carrying its holder and a heartbeat, so a worker that dies
does not wedge the queue forever.
"""

from __future__ import annotations

import json
import os
import socket
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import DATA

JOBS_DIR = DATA / "jobs"

# Set by the deployment. The queue is read by the API and written by the worker,
# which are different containers, so on AWS it lives in S3 rather than on either
# one's disk.
JOBS_BUCKET_ENV = "APPLEBEE_JOBS_BUCKET"
JOBS_PREFIX = "jobs"
LOCK_NAME = "worker.lock.json"

# A worker refreshes the lock as it goes; a lock older than this is treated as
# abandoned. Generous, because a legitimate weather fetch runs for hours.
LOCK_STALE_SECONDS = 30 * 60

REQUESTED, APPROVED, RUNNING, DONE, FAILED, REJECTED = (
    "requested", "approved", "running", "done", "failed", "rejected")

KINDS = {
    # kind        -> required parameters
    "weather": ("region", "start", "end"),
    "forage": ("region", "years"),
}


class Locked(RuntimeError):
    """Another worker holds the lock. There is only ever meant to be one."""


class Storage:
    """Where job records live. A directory locally, a bucket in the deployment.

    The only operation that has to be more than a read or a write is
    :meth:`write_if_absent`, which is the lock: it must fail rather than
    overwrite, atomically, or two workers can both believe they hold it.
    """

    def read(self, name: str) -> bytes | None: ...
    def write(self, name: str, data: bytes) -> None: ...
    def write_if_absent(self, name: str, data: bytes) -> bool: ...
    def delete(self, name: str) -> None: ...
    def names(self) -> list[str]: ...


class LocalStorage(Storage):
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def read(self, name):
        path = self.root / name
        return path.read_bytes() if path.exists() else None

    def write(self, name, data):
        (self.root / name).write_bytes(data)

    def write_if_absent(self, name, data):
        try:
            handle = os.open(self.root / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        with os.fdopen(handle, "wb") as out:
            out.write(data)
        return True

    def delete(self, name):
        (self.root / name).unlink(missing_ok=True)

    def names(self):
        return sorted(p.name for p in self.root.glob("*.json"))


class S3Storage(Storage):
    """The same, in a bucket.

    ``write_if_absent`` uses a conditional put, so the lock is as atomic in S3
    as an exclusive create is on a filesystem.
    """

    def __init__(self, bucket: str, prefix: str = JOBS_PREFIX):
        import boto3

        self.bucket, self.prefix, self.s3 = bucket, prefix, boto3.client("s3")

    def _key(self, name: str) -> str:
        return f"{self.prefix}/{name}"

    def read(self, name):
        import botocore

        try:
            return self.s3.get_object(Bucket=self.bucket, Key=self._key(name))["Body"].read()
        except botocore.exceptions.ClientError:
            return None

    def write(self, name, data):
        self.s3.put_object(Bucket=self.bucket, Key=self._key(name), Body=data)

    def write_if_absent(self, name, data):
        import botocore

        try:
            self.s3.put_object(Bucket=self.bucket, Key=self._key(name), Body=data,
                               IfNoneMatch="*")
            return True
        except botocore.exceptions.ClientError as exc:
            if exc.response["Error"]["Code"] in ("PreconditionFailed", "ConditionalRequestConflict"):
                return False
            raise

    def delete(self, name):
        self.s3.delete_object(Bucket=self.bucket, Key=self._key(name))

    def names(self):
        pages = self.s3.get_paginator("list_objects_v2")
        return sorted(
            obj["Key"].rsplit("/", 1)[-1]
            for page in pages.paginate(Bucket=self.bucket, Prefix=f"{self.prefix}/")
            for obj in page.get("Contents", [])
            if obj["Key"].endswith(".json")
        )


def storage_for(root: Path | None = None) -> Storage:
    """S3 when the deployment names a bucket, a directory otherwise."""
    bucket = os.environ.get(JOBS_BUCKET_ENV)
    if bucket and root is None:
        return S3Storage(bucket)
    return LocalStorage(root or JOBS_DIR)


@dataclass
class Job:
    id: str
    kind: str
    parameters: dict
    state: str = REQUESTED
    requested_by: str = ""
    requested_at: float = 0.0
    history: list = field(default_factory=list)
    note: str = ""

    @property
    def runnable(self) -> bool:
        return self.state == APPROVED


class JobStore:
    """Durable job state. One JSON file per job, one lock for the worker."""

    def __init__(self, root: Path | None = None, storage: Storage | None = None):
        # Resolved at call time, not at import, so a deployment (or a test) can
        # point the queue somewhere else without reaching inside the class.
        self.store = storage or storage_for(root)

    # -- requesting ---------------------------------------------------------

    def request(self, kind: str, *, requested_by: str = "", **parameters) -> Job:
        if kind not in KINDS:
            raise ValueError(f"unknown job kind {kind!r}; expected {sorted(KINDS)}")
        missing = [p for p in KINDS[kind] if p not in parameters]
        if missing:
            raise ValueError(f"{kind} job needs {missing}")
        job = Job(id=uuid.uuid4().hex[:12], kind=kind, parameters=parameters,
                  requested_by=requested_by, requested_at=time.time())
        self._write(job, "requested")
        return job

    def plan(self, job_id: str) -> dict:
        """What a job would cost, without making a single request.

        Answered before approval, because "about seven hours and 10 GB" is the
        thing an administrator needs to know and the thing a requester rarely
        guesses.
        """
        job = self.get(job_id)
        if job.kind == "weather":
            from .acquire import prism

            return prism.estimate(DATA / "rasters", ("tmean", "ppt"),
                                  job.parameters["start"], job.parameters["end"])
        years = list(job.parameters["years"])
        # One national CDL raster per year: ~3 GB and ~12 minutes each, measured
        # when the 2013-2018 index was built.
        return {"years": len(years), "approx_GB": round(3.0 * len(years), 1),
                "approx_hours": round(0.2 * len(years), 1)}

    # -- deciding -----------------------------------------------------------

    def approve(self, job_id: str, by: str = "") -> Job:
        return self._transition(job_id, APPROVED, {REQUESTED}, by=by)

    def reject(self, job_id: str, by: str = "", note: str = "") -> Job:
        return self._transition(job_id, REJECTED, {REQUESTED}, by=by, note=note)

    # -- running ------------------------------------------------------------

    def claim(self, worker: str | None = None) -> Job | None:
        """Take the oldest approved job, under the lock. None if there is none.

        The lock is taken before the job is chosen, so two workers starting at
        once cannot both decide to fetch.
        """
        worker = worker or f"{socket.gethostname()}:{os.getpid()}"
        self.acquire_lock(worker)
        try:
            approved = sorted((j for j in self.list() if j.runnable),
                              key=lambda j: j.requested_at)
            if not approved:
                self.release_lock()
                return None
            return self._transition(approved[0].id, RUNNING, {APPROVED}, by=worker)
        except Exception:
            self.release_lock()
            raise

    def finish(self, job_id: str, ok: bool, note: str = "") -> Job:
        job = self._transition(job_id, DONE if ok else FAILED, {RUNNING}, note=note)
        self.release_lock()
        return job

    # -- the lock -----------------------------------------------------------

    def acquire_lock(self, holder: str) -> None:
        held = self.store.read(LOCK_NAME)
        if held is not None:
            age = time.time() - json.loads(held).get("at", 0)
            if age < LOCK_STALE_SECONDS:
                raise Locked(f"another worker holds the lock ({age:.0f}s old)")
            self.store.delete(LOCK_NAME)    # abandoned: a worker died mid-job
        record = json.dumps({"holder": holder, "at": time.time()}).encode()
        if not self.store.write_if_absent(LOCK_NAME, record):
            raise Locked("another worker took the lock first")

    def heartbeat(self) -> None:
        """Say the worker is still alive, so a long fetch is not called dead."""
        held = self.store.read(LOCK_NAME)
        if held is not None:
            record = json.loads(held)
            record["at"] = time.time()
            self.store.write(LOCK_NAME, json.dumps(record).encode())

    def release_lock(self) -> None:
        self.store.delete(LOCK_NAME)

    # -- reading ------------------------------------------------------------

    def get(self, job_id: str) -> Job:
        raw = self.store.read(f"{job_id}.json")
        if raw is None:
            raise KeyError(f"no job {job_id!r}")
        return Job(**json.loads(raw))

    def list(self, state: str | None = None) -> list[Job]:
        jobs = [Job(**json.loads(self.store.read(name)))
                for name in self.store.names() if name != LOCK_NAME]
        return [j for j in jobs if state is None or j.state == state]

    # -- internals ----------------------------------------------------------

    def _transition(self, job_id: str, state: str, allowed_from: set,
                    by: str = "", note: str = "") -> Job:
        job = self.get(job_id)
        if job.state not in allowed_from:
            raise ValueError(
                f"job {job_id} is {job.state!r}; {state!r} needs one of {sorted(allowed_from)}"
            )
        job.state = state
        if note:
            job.note = note
        self._write(job, state, by=by)
        return job

    def _write(self, job: Job, event: str, by: str = "") -> None:
        job.history.append({"state": event, "at": time.time(), "by": by})
        self.store.write(f"{job.id}.json", json.dumps(asdict(job), indent=1).encode())


def command(job: Job) -> list[str]:
    """The command that carries a job out, as the existing scripts spell it.

    Returned rather than run, so an administrator sees exactly what will happen
    and the worker has nothing of its own to get wrong.
    """
    if job.kind == "weather":
        return ["python", "scripts/fetch_prism.py",
                "--region", job.parameters["region"],
                "--start", job.parameters["start"], "--end", job.parameters["end"]]
    years = list(job.parameters["years"])
    return ["python", "scripts/build_forage.py", "--region", job.parameters["region"],
            "--years", str(min(years)), str(max(years))]
