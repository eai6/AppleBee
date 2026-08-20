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
LOCK_FILE = JOBS_DIR / "worker.lock"

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

    def __init__(self, root: Path | None = None):
        # Resolved at call time, not at import, so a deployment (or a test) can
        # point the queue somewhere else without reaching inside the class.
        self.root = Path(root or JOBS_DIR)
        self.root.mkdir(parents=True, exist_ok=True)

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
        lock = self.root / LOCK_FILE.name
        if lock.exists():
            age = time.time() - json.loads(lock.read_text()).get("at", 0)
            if age < LOCK_STALE_SECONDS:
                raise Locked(f"another worker holds the lock ({age:.0f}s old)")
            lock.unlink()          # abandoned: a worker died mid-job
        try:
            handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise Locked("another worker took the lock first") from None
        with os.fdopen(handle, "w") as out:
            json.dump({"holder": holder, "at": time.time()}, out)

    def heartbeat(self) -> None:
        """Say the worker is still alive, so a long fetch is not called dead."""
        lock = self.root / LOCK_FILE.name
        if lock.exists():
            record = json.loads(lock.read_text())
            record["at"] = time.time()
            lock.write_text(json.dumps(record))

    def release_lock(self) -> None:
        (self.root / LOCK_FILE.name).unlink(missing_ok=True)

    # -- reading ------------------------------------------------------------

    def get(self, job_id: str) -> Job:
        path = self.root / f"{job_id}.json"
        if not path.exists():
            raise KeyError(f"no job {job_id!r}")
        return Job(**json.loads(path.read_text()))

    def list(self, state: str | None = None) -> list[Job]:
        jobs = [Job(**json.loads(p.read_text()))
                for p in sorted(self.root.glob("*.json")) if p.name != LOCK_FILE.name]
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
        (self.root / f"{job.id}.json").write_text(json.dumps(asdict(job), indent=1))


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
