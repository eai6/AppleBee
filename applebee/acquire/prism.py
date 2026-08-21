"""Download daily PRISM 4 km weather and sample it onto the model grid.

PRISM serves one CONUS raster per variable per day from a public endpoint that
needs no key::

    https://services.nacse.org/prism/data/get/us/4km/{variable}/{YYYYMMDD}

Each response is a ~2 MB zip holding a ``.bil`` raster and its header.

**PRISM's download limits are strict, and worth reading before running anything
here.** From their web service documentation:

    Download activity is continuously monitored. To prevent rogue download
    scripts from exceeding bandwidth limits, if a file is downloaded twice in a
    24-hour period, no more downloads of that file will be allowed during that
    period. Repeated excessive download activity may result in IP address
    blocking, at our discretion.

So a file may be fetched **twice per 24 hours**, and hammering the service gets
the IP blocked -- which presents as a TCP connect timeout, not an HTTP error.
Everything here is built around that: downloads are skipped when the file is
already on disk, requests are paced by default, and a run can be interrupted and
resumed without re-fetching. Call :func:`estimate` before a large fetch.

The output is written straight to the ``(n_cells, n_days)`` float32 cache that
:mod:`applebee.weather` reads. The wide per-day CSV the archived workflow
produced is skipped entirely -- it existed only as an intermediate, and at
Northeast extent it would be tens of gigabytes.
"""

from __future__ import annotations

import io
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from ..config import CACHE
from .grid import cells_in_bbox

PRISM_URL = "https://services.nacse.org/prism/data/get/us/4km/{variable}/{stamp}"
VARIABLES = ("tmean", "ppt", "tmin", "tmax")

# PRISM publishes each day at increasing quality: early, then provisional within
# six months, then stable. Filenames carry the tag, which is how a cached day can
# be checked for whether a better release now exists.
QUALITY_ORDER = ("early", "provisional", "stable")

# Deliberately unhurried. A day of one variable is ~2 MB, so a 17-year two-variable
# fetch is ~25 GB and will take many hours whatever the pause -- there is nothing
# to gain by crowding a service that blocks IPs for it.
DEFAULT_PAUSE_SECONDS = 3.0

# Separate connect and read timeouts: once PRISM blocks an IP the TCP connect
# hangs, so a short connect timeout is what surfaces a block quickly.
DEFAULT_TIMEOUT = (10, 180)


class RateLimited(RuntimeError):
    """PRISM refused or throttled the request.

    Their limit is two downloads of the same file per 24 hours, with IP blocking
    for repeated excessive activity. A block appears as a connect timeout.
    """


@dataclass
class FetchReport:
    downloaded: int
    skipped: int
    failed: dict[str, str]

    def __str__(self) -> str:
        return (f"downloaded {self.downloaded}, skipped {self.skipped} already held, "
                f"{len(self.failed)} failed")


def _day_dir(root: Path, variable: str, day: pd.Timestamp) -> Path:
    return root / variable / f"{day.year}" / f"PRISM_{variable}_{day:%Y%m%d}"


# PRISM changed the delivery format: the archived exports are ESRI BIL
# (``PRISM_tmean_stable_4kmD2_20150501_bil.bil``) while the service now returns
# GeoTIFF (``prism_tmean_us_25m_20150501.tif`` -- "25m" is 2.5 arc-minutes, the
# same 1/24 degree grid). Verified bit-identical: same 621 x 1405 extent, same
# nodata, and a maximum difference of 0.000000 degC across 481,631 cells. Both
# are read here so archived and freshly fetched days interoperate.
RASTER_SUFFIXES = ("*.tif", "*.bil")


def _raster_in(directory: Path) -> Path | None:
    for pattern in RASTER_SUFFIXES:
        found = next(iter(sorted(directory.glob(pattern))), None)
        if found is not None:
            return found
    return None


def already_have(root: Path, variable: str, day: pd.Timestamp) -> bool:
    """True if a raster for this variable-day is already unpacked on disk."""
    target = _day_dir(root, variable, day)
    return target.is_dir() and _raster_in(target) is not None


def download_day(
    root: Path,
    variable: str,
    day: pd.Timestamp,
    session: requests.Session | None = None,
    timeout=DEFAULT_TIMEOUT,
) -> Path:
    """Fetch and unpack one PRISM day. Returns the directory holding the ``.bil``.

    Returns immediately if the day is already unpacked -- never re-requests a
    file, because PRISM allows only two fetches of it per 24 hours.

    Raises:
        RateLimited: if PRISM refuses the request or the connection times out,
            which is how an IP block presents.
    """
    if variable not in VARIABLES:
        raise ValueError(f"variable must be one of {VARIABLES}, got {variable!r}")
    day = pd.Timestamp(day)
    target = _day_dir(root, variable, day)
    if already_have(root, variable, day):
        return target

    url = PRISM_URL.format(variable=variable, stamp=f"{day:%Y%m%d}")
    getter = session or requests
    try:
        response = getter.get(url, timeout=timeout)
    except requests.exceptions.ConnectTimeout as exc:
        raise RateLimited(
            f"could not connect to PRISM for {variable} {day:%Y-%m-%d}. A connect "
            "timeout usually means the IP is blocked after excessive requests; "
            "PRISM lifts these at their discretion, so wait before retrying."
        ) from exc
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "")
    if "zip" not in content_type:
        # PRISM answers an exceeded limit, or a day it does not hold, with HTML.
        raise RateLimited(
            f"{url} returned {content_type!r} rather than a zip. Either this file "
            "has already been downloaded twice in the past 24 hours, or the date "
            f"is not available. First bytes: {response.content[:160]!r}"
        )

    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        archive.extractall(target)
    return target


def fetch_with_retry(
    root: Path,
    variable: str,
    day: pd.Timestamp,
    session: requests.Session | None = None,
    attempts: int = 4,
    backoff: float = 15.0,
) -> tuple[bool, str]:
    """Fetch one day, retrying transient network faults.

    A long run meets more than rate limiting: the server drops connections
    (``RemoteDisconnected``), resets, and times out mid-read. Those are transient
    and worth retrying -- an unhandled one killed a 5-hour run after eight days.
    Rate limiting is *not* retried here, because it does not clear in seconds.

    Returns:
        ``(ok, message)``. ``ok`` is False for a genuine failure.
    """
    last = ""
    for attempt in range(1, attempts + 1):
        try:
            download_day(root, variable, day, session=session)
            return True, ""
        except RateLimited as exc:
            return False, f"RateLimited: {exc}"
        except (requests.exceptions.RequestException, zipfile.BadZipFile, OSError) as exc:
            last = f"{type(exc).__name__}: {exc}"
            if attempt < attempts:
                time.sleep(backoff * attempt)
    return False, f"after {attempts} attempts: {last}"


def estimate(root: Path, variables=("tmean", "ppt"), start="2008-01-01", end="2024-12-31") -> dict:
    """How much work a fetch would be, without making a single request.

    Call this before :func:`download_range`. At roughly 2 MB per variable-day,
    a Northeast-scale multi-year fetch runs to tens of gigabytes and many hours.
    """
    root = Path(root)
    days = pd.date_range(start, end, freq="D")
    needed = sum(
        1 for variable in variables for day in days if not already_have(root, variable, day)
    )
    total = len(days) * len(variables)
    return {
        "variable_days_total": total,
        "already_held": total - needed,
        "to_download": needed,
        "approx_GB": round(needed * 2.1 / 1024, 2),
        "approx_hours_at_default_pause": round(needed * (DEFAULT_PAUSE_SECONDS + 1.5) / 3600, 1),
    }


def download_range(
    root: Path,
    variables=("tmean", "ppt"),
    start="2008-01-01",
    end="2024-12-31",
    pause: float = DEFAULT_PAUSE_SECONDS,
    progress: bool = True,
) -> FetchReport:
    """Fetch every variable-day in a range, skipping anything already held.

    Safe to interrupt and rerun: completed days are detected on disk.
    """
    root = Path(root)
    days = pd.date_range(start, end, freq="D")
    downloaded = skipped = 0
    consecutive_limits = 0
    failed: dict[str, str] = {}

    with requests.Session() as session:
        for variable in variables:
            for n, day in enumerate(days, start=1):
                if already_have(root, variable, day):
                    skipped += 1
                    continue
                ok, message = fetch_with_retry(root, variable, day, session=session)
                if ok:
                    downloaded += 1
                    consecutive_limits = 0
                    time.sleep(pause)
                else:
                    failed[f"{variable} {day:%Y-%m-%d}"] = message
                    consecutive_limits += 1
                    # Stop only on sustained failure -- a single dropped
                    # connection must not end a multi-hour fetch.
                    if consecutive_limits >= 5:
                        print("stopping: five consecutive failures. Already-downloaded "
                              "days are kept, so rerunning resumes where this left off.",
                              flush=True)
                        return FetchReport(downloaded, skipped, failed)
                    time.sleep(pause * 5)
                if progress and n % 200 == 0:
                    print(f"  {variable} {day:%Y-%m-%d}: {downloaded} fetched, "
                          f"{skipped} skipped, {len(failed)} failed", flush=True)

    return FetchReport(downloaded, skipped, failed)


def _read_raster(directory: Path) -> tuple[np.ndarray, dict]:
    """Read a PRISM day raster into an array, honouring its nodata value.

    Accepts either delivery format; see :data:`RASTER_SUFFIXES`.
    """
    import rasterio

    raster = _raster_in(directory)
    if raster is None:
        raise FileNotFoundError(f"no {' or '.join(RASTER_SUFFIXES)} in {directory}")
    with rasterio.open(raster) as src:
        values = src.read(1).astype("float32")
        if src.nodata is not None:
            values[values == src.nodata] = np.nan
        return values, {"transform": src.transform, "shape": src.shape}


def sample_to_cells(
    root: Path,
    variable: str,
    days,
    cells: pd.DataFrame,
) -> np.ndarray:
    """Sample daily rasters at grid-cell centres.

    Args:
        root: Download root used by :func:`download_range`.
        variable: PRISM variable name.
        days: Dates to read, in the order the columns should appear.
        cells: Frame with ``col``/``row`` grid indices (see :mod:`.grid`).

    Returns:
        ``(n_cells, n_days)`` float32 array. Days missing from disk are NaN.

    The PRISM ``.bil`` grid *is* the model grid, so this is a direct index rather
    than an interpolation: raster row/column equal the ``(row, col)`` keys.
    """
    root = Path(root)
    days = pd.DatetimeIndex(days)
    rows = cells["row"].to_numpy(dtype=int)
    cols = cells["col"].to_numpy(dtype=int)
    out = np.full((len(cells), len(days)), np.nan, dtype="float32")

    for j, day in enumerate(days):
        directory = _day_dir(root, variable, day)
        if not (directory.is_dir() and _raster_in(directory) is not None):
            continue
        raster, meta = _read_raster(directory)
        n_rows, n_cols = meta["shape"]
        valid = (rows >= 0) & (rows < n_rows) & (cols >= 0) & (cols < n_cols)
        out[valid, j] = raster[rows[valid], cols[valid]]
    return out


def build_cache(
    root: Path,
    cache_key: str,
    cells: pd.DataFrame,
    variable: str,
    start: str,
    end: str,
    cache_dir: Path | None = None,
) -> Path:
    """Sample a date range onto ``cells`` and write the model's cache files.

    Writes ``{cache_key}.values.npy``, ``.dates.npy`` and ``.cells.parquet``,
    which is exactly what :func:`applebee.weather.load_weather` memory-maps.
    """
    cache_dir = Path(cache_dir or CACHE)
    cache_dir.mkdir(parents=True, exist_ok=True)
    days = pd.date_range(start, end, freq="D")

    values = sample_to_cells(root, variable, days, cells)
    missing = int(np.isnan(values).all(axis=0).sum())
    if missing:
        print(f"warning: {missing} of {len(days)} days had no raster on disk", flush=True)

    np.save(cache_dir / f"{cache_key}.values.npy", values)
    np.save(cache_dir / f"{cache_key}.dates.npy", days.to_numpy())
    cells[["col", "row", "lon", "lat"]].reset_index(drop=True).to_parquet(
        cache_dir / f"{cache_key}.cells.parquet"
    )
    return cache_dir / f"{cache_key}.values.npy"


def region_cells(bbox) -> pd.DataFrame:
    """Convenience wrapper so callers need only import this module."""
    return cells_in_bbox(bbox)


# Days buffered before writing to the memmap. 256 days x 481,631 cells x 4 bytes
# is about 500 MB, which stays comfortably inside RAM.
BLOCK_DAYS = 256


def _flush(values, buffer_cols, buffer_index) -> None:
    """Write buffered day-columns into the memmap as contiguous runs."""
    if not buffer_cols:
        return
    order = np.argsort(buffer_index)
    cols_sorted = [buffer_cols[k] for k in order]
    idx_sorted = [buffer_index[k] for k in order]
    start = 0
    while start < len(idx_sorted):
        stop = start + 1
        while stop < len(idx_sorted) and idx_sorted[stop] == idx_sorted[stop - 1] + 1:
            stop += 1
        block = np.stack(cols_sorted[start:stop], axis=1)
        values[:, idx_sorted[start]:idx_sorted[stop - 1] + 1] = block
        start = stop
    values.flush()
    buffer_cols.clear()
    buffer_index.clear()


def extend_matrix(cache_dir: Path, cache_key: str, start: str, end: str) -> dict:
    """Grow a cached matrix's day axis, keeping the days already in it.

    :func:`fetch_and_sample` sizes its array to the range it is asked for and
    throws away a cache of a different shape, so asking for 2013-2025 on top of
    a 2013-2018 cache would re-fetch six years that are already held -- about
    twelve hours of PRISM's pacing, for nothing. This copies the existing days
    into a matrix of the new shape first; the resume scan then skips them.

    The new range must start no later than the old one and end no earlier, so
    that every day already held still has a home.
    """
    cache_dir = Path(cache_dir)
    values_path = cache_dir / f"{cache_key}.values.npy"
    dates_path = cache_dir / f"{cache_key}.dates.npy"
    if not values_path.exists():
        return {"extended": False, "reason": "nothing cached yet"}

    old_days = pd.DatetimeIndex(np.load(dates_path))
    new_days = pd.date_range(start, end, freq="D")
    if old_days[0] < new_days[0] or old_days[-1] > new_days[-1]:
        raise ValueError(
            f"{cache_key}: {start}..{end} does not contain the cached "
            f"{old_days[0]:%Y-%m-%d}..{old_days[-1]:%Y-%m-%d}"
        )
    if len(old_days) == len(new_days):
        return {"extended": False, "reason": "already the requested range"}

    offset = int(new_days.get_loc(old_days[0]))
    existing = np.lib.format.open_memmap(values_path, mode="r")
    grown_path = values_path.with_suffix(".growing.npy")
    grown = np.lib.format.open_memmap(
        grown_path, mode="w+", dtype=existing.dtype,
        shape=(existing.shape[0], len(new_days)))
    grown[:] = np.nan
    # Copied in blocks: the whole array is gigabytes and does not want to be
    # resident all at once.
    for first in range(0, existing.shape[0], 8192):
        last = min(first + 8192, existing.shape[0])
        grown[first:last, offset:offset + existing.shape[1]] = existing[first:last]
    del existing, grown
    grown_path.replace(values_path)
    np.save(dates_path, new_days.to_numpy())
    return {"extended": True, "days_before": len(old_days), "days_after": len(new_days),
            "offset": offset}


def fetch_and_sample(
    root: Path,
    cache_key: str,
    cells: pd.DataFrame,
    variable: str,
    start: str,
    end: str,
    keep_rasters: bool = True,
    pause: float = DEFAULT_PAUSE_SECONDS,
    cache_dir: Path | None = None,
    progress: bool = True,
) -> dict:
    """Download, sample and cache one variable in a single pass.

    Each PRISM file is a CONUS-wide raster, so the *download* cost depends only
    on the number of days -- asking for the Northeast costs exactly what asking
    for one cell does. Only the sampling step depends on how many cells you keep.

    Args:
        keep_rasters: False deletes each ``.bil`` once sampled, holding disk to
            the size of the cache. Weigh that against PRISM's two-downloads-per-
            file-per-24-hours rule: discarding a raster means a different region
            cannot be sampled from it later without re-fetching. Keeping them is
            the safer default; discard only when disk is the binding constraint.

    Returns:
        Counts of days fetched, reused from disk and missing.
    """
    import shutil

    root = Path(root)
    cache_dir = Path(cache_dir or CACHE)
    cache_dir.mkdir(parents=True, exist_ok=True)
    days = pd.date_range(start, end, freq="D")

    rows = cells["row"].to_numpy(dtype=int)
    cols = cells["col"].to_numpy(dtype=int)

    # Written straight to the .npy via memmap rather than held in RAM. At CONUS
    # extent the array is 4.2 GB per variable, which would swap on a typical
    # machine; this also means an interrupted run leaves the days it completed.
    values_path = cache_dir / f"{cache_key}.values.npy"
    shape = (len(cells), len(days))
    resume = np.zeros(len(days), dtype=bool)
    if values_path.exists():
        try:
            existing = np.lib.format.open_memmap(values_path, mode="r")
            if existing.shape == shape:
                # A day counts as written when every cell that *can* carry data
                # does. Two mistakes are possible here and both have been made:
                #
                #   Sampling a couple of rows is not enough -- an interrupted run
                #   leaves a column half written, the north populated and the
                #   south still NaN, and a two-row check calls that day complete,
                #   baking a band of missing data into the cache.
                #
                #   Requiring *every* cell to be finite is not right either. Over
                #   half this grid is ocean, Canada, or outside PRISM's land mask
                #   and is NaN on every day of a perfectly complete matrix, so no
                #   day ever qualifies and a resumed run re-fetches everything it
                #   already holds -- twelve hours of PRISM's pacing for nothing,
                #   and a real risk of being rate-limited for it.
                #
                # So completeness is judged against the fullest day present,
                # which is the land mask as this matrix knows it.
                filled = np.zeros(len(days), dtype=int)
                for j in range(len(days)):
                    filled[j] = int(np.isfinite(existing[:, j]).sum())
                land = int(filled.max())
                resume = (filled >= land * 0.999) & (land > 0)
                del existing
                values = np.lib.format.open_memmap(values_path, mode="r+")
                print(f"  resuming: {int(resume.sum()):,} of {len(days):,} days already written",
                      flush=True)
            else:
                del existing
                values = None
        except (ValueError, OSError):
            values = None
    else:
        values = None
    if values is None:
        values = np.lib.format.open_memmap(values_path, mode="w+", dtype="float32", shape=shape)
        values[:] = np.nan
        resume = np.zeros(len(days), dtype=bool)
    fetched = reused = missing = skipped_days = 0
    consecutive_limits = 0
    buffer_cols: list[np.ndarray] = []
    buffer_index: list[int] = []

    with requests.Session() as session:
        for j, day in enumerate(days):
            if resume[j]:
                skipped_days += 1
                continue
            held = already_have(root, variable, day)
            if not held:
                ok, message = fetch_with_retry(root, variable, day, session=session)
                if not ok:
                    missing += 1
                    consecutive_limits += 1
                    # Only sustained failure stops the run; an isolated dropped
                    # connection must not end a multi-hour fetch.
                    if consecutive_limits >= 5:
                        print(f"stopping at {day:%Y-%m-%d}: five consecutive failures "
                              f"({message}). Days already fetched are kept, so rerunning "
                              "resumes from here.", flush=True)
                        break
                    time.sleep(pause * 5)
                    continue
                fetched += 1
                consecutive_limits = 0
                time.sleep(pause)
            else:
                reused += 1

            directory = _day_dir(root, variable, day)
            raster, meta = _read_raster(directory)
            n_rows, n_cols = meta["shape"]
            valid = (rows >= 0) & (rows < n_rows) & (cols >= 0) & (cols < n_cols)
            column = np.full(len(cells), np.nan, dtype="float32")
            column[valid] = raster[rows[valid], cols[valid]]

            # Buffer days and write in blocks. Writing one column at a time
            # dirties a page for every cell across the whole file, and once the
            # array outgrows free RAM the page cache thrashes -- that took the
            # CONUS run from 0.04 s to ~29 s per day. Blocks keep each row's
            # write inside a page or two.
            buffer_cols.append(column)
            buffer_index.append(j)
            if len(buffer_cols) >= BLOCK_DAYS:
                _flush(values, buffer_cols, buffer_index)

            if not keep_rasters:
                shutil.rmtree(directory, ignore_errors=True)
            if progress and (j + 1) % 100 == 0:
                print(f"  {variable} {day:%Y-%m-%d}  fetched {fetched}, reused {reused}, "
                      f"missing {missing}", flush=True)

    _flush(values, buffer_cols, buffer_index)
    nbytes = values.nbytes
    values.flush()
    del values
    np.save(cache_dir / f"{cache_key}.dates.npy", days.to_numpy())
    cells[["col", "row", "lon", "lat"]].reset_index(drop=True).to_parquet(
        cache_dir / f"{cache_key}.cells.parquet"
    )
    return {"fetched": fetched, "reused": reused, "missing": missing,
            "already_written": skipped_days, "days": len(days), "cells": len(cells),
            "cache_MB": round(nbytes / 1e6, 1)}
