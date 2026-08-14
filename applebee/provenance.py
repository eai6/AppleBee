"""Where every input came from, and whether it is still the file that arrived.

Each region under ``data/inputs/`` carries a ``PROVENANCE.json`` recording its
source URL, coverage, how it was validated, and a size and SHA-256 for every
file. Those records are tracked in git even where the bytes are far too large to
commit, so a reader who rebuilds an input from its documented source can check
the result against the same digest the analysis used.

    from applebee import provenance
    provenance.summary()             # what each input is, and where it came from
    provenance.verify()              # sizes -- seconds
    provenance.verify(full=True)     # SHA-256 -- minutes, reads every byte

``verify`` compares what is on disk against the record. A ``changed`` row means
the file is not the one the record describes; a ``missing`` row means it was
never fetched, and the ``rebuild`` column in :func:`summary` says how to get it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from .config import INPUTS

CHUNK = 8 << 20  # 8 MB, so hashing a multi-gigabyte matrix does not load it


def records(root: Path = INPUTS) -> dict[str, dict]:
    """Every ``PROVENANCE.json`` under ``data/inputs``, keyed by its directory."""
    return {p.parent.relative_to(root).as_posix(): json.loads(p.read_text())
            for p in sorted(root.rglob("PROVENANCE.json"))}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(CHUNK):
            digest.update(block)
    return digest.hexdigest()


def summary(root: Path = INPUTS) -> pd.DataFrame:
    """One row per documented input: what it is, its source, and how to rebuild it."""
    rows = []
    for key, rec in records(root).items():
        files = rec.get("files", {})
        rows.append({
            "input": key,
            "dataset": rec.get("dataset", ""),
            "source": rec.get("source", ""),
            "retrieved": rec.get("retrieved", rec.get("provenance", "")),
            "period": rec.get("period", ""),
            "files": len(files),
            "GB": round(sum(f.get("bytes", 0) for f in files.values()) / 1e9, 2),
            "rebuild": rec.get("rebuild", rec.get("rebuild_cost", "")),
            "validated": rec.get("verified", ""),
        })
    return pd.DataFrame(rows)


def verify(name: str | None = None, *, full: bool = False,
           root: Path = INPUTS) -> pd.DataFrame:
    """Check inputs against their recorded size and, with ``full``, SHA-256.

    Args:
        name: Restrict to one record, e.g. ``"weather/conus"``. All by default.
        full: Also hash every byte. Correct but slow -- the CONUS matrices alone
            are 8.4 GB, so this is minutes, not seconds.
        root: Directory to search; defaults to ``data/inputs``.

    Returns:
        One row per file, with a ``status`` of ``ok``, ``missing``, ``changed``
        or ``size ok, not hashed``.
    """
    rows = []
    for key, rec in records(root).items():
        if name and key != name:
            continue
        for filename, meta in rec.get("files", {}).items():
            path = root / key / filename
            row = {"input": key, "file": filename, "GB": round(meta.get("bytes", 0) / 1e9, 3)}
            if not path.exists():
                rows.append({**row, "status": "missing"})
                continue
            if path.stat().st_size != meta.get("bytes"):
                rows.append({**row, "status": "changed"})  # size alone settles it
                continue
            if not full:
                rows.append({**row, "status": "size ok, not hashed"})
                continue
            rows.append({**row,
                         "status": "ok" if sha256(path) == meta.get("sha256") else "changed"})
    return pd.DataFrame(rows)


def report(name: str | None = None, *, full: bool = False, root: Path = INPUTS) -> pd.DataFrame:
    """:func:`verify`, printed as a verdict. Returns the same frame."""
    frame = verify(name, full=full, root=root)
    if frame.empty:
        print("no provenance records found")
        return frame
    counts = frame.status.value_counts()
    checked = "SHA-256" if full else "size"
    print(f"{len(frame)} files checked by {checked}: "
          + ", ".join(f"{n} {s}" for s, n in counts.items()))
    bad = frame[frame.status.isin(["missing", "changed"])]
    if len(bad):
        print("\n" + bad.to_string(index=False))
    return frame
