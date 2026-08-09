"""Build the Lonsdorf spring floral resource index from the Cropland Data Layer.

The index is the area-weighted mean of Koh et al. (2016) expert spring-forage
values over the CDL land-cover classes within a radius of each grid-cell centre.
That is the method behind ``Forage_spring_1km`` in the archived Pennsylvania
inputs, and behind the PSU beeshiny service the archived workflow used.

Reimplemented locally so the extent is not limited to what was uploaded to that
service by hand. Validated against ``archives/data/forage.csv`` for 2021 on a
60-cell sample: r = 0.985 (1 km), 0.990 (3 km), 0.992 (5 km), mean absolute
difference 0.009-0.015. Residual differences are consistent with beeshiny running
a different CDL vintage.

**Mosaic, do not clip.** The state CDL rasters stop at the state line, so a
buffer straddling a border loses whatever falls outside. One archived
Pennsylvania cell sits outside the PA raster entirely. Every state adjoining the
region of interest must therefore be included in the mosaic, even if no grid
cells are wanted there.

Steps, mirroring ``terra::classify`` + ``exactextractr::exact_extract``:

1. Fetch the CDL GeoTIFF per state-year (EPSG:5070, 30 m).
2. Buffer each cell centre by the foraging radius **in the raster CRS**.
3. Take the area fraction of every land-cover class within the buffer.
4. Dot those fractions with the Koh spring index.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from ..config import ARCHIVES

CDL_SERVICE = "https://nassgeodata.gmu.edu/axis2/services/CDLService/GetCDLFile"

# NAD83 / Conus Albers -- the CRS the CDL ships in, and the one buffers must be
# built in so that a radius in metres means what it says.
CDL_CRS = "EPSG:5070"

# Koh et al. (2016) expert values per CDL class.
KOH_TABLE = ARCHIVES / "data" / "CDL" / "cdl_reclass_koh.csv"
SPRING_COLUMN = "floral_resources_spring_index"

DEFAULT_RADII_M = (1000, 3000, 5000)

# CDL classes are 0-255; class 0 is Background, which scores zero.
_LUT_SIZE = 256

STATE_FIPS = {
    "CT": 9, "DE": 10, "MA": 25, "MD": 24, "ME": 23, "NH": 33, "NJ": 34,
    "NY": 36, "PA": 42, "RI": 44, "VT": 50, "WV": 54, "VA": 51,
    "OH": 39, "NC": 37, "KY": 21,
}


def load_koh_lookup(column: str = SPRING_COLUMN, path: Path = KOH_TABLE) -> np.ndarray:
    """Koh expert values as a 256-entry lookup indexed by CDL class."""
    table = pd.read_csv(path)
    if column not in table.columns:
        raise ValueError(f"{path.name} has no column {column!r}")
    lookup = np.zeros(_LUT_SIZE, dtype="float64")
    values = table["value"].to_numpy(dtype=int)
    if values.min() < 0 or values.max() >= _LUT_SIZE:
        raise ValueError(f"CDL class values outside 0-{_LUT_SIZE - 1} in {path.name}")
    lookup[values] = table[column].to_numpy(dtype=float)
    return lookup


NATIONAL_URL = (
    "https://www.nass.usda.gov/Research_and_Science/Cropland/Release/datasets/"
    "{year}_30m_cdls.zip"
)


def download_national_cdl(year: int, dest: Path, timeout: int = 300, chunk: int = 1 << 22) -> Path:
    """Fetch the CONUS-wide CDL for one year from USDA, ~1.9 GB zipped.

    Preferred over the per-state rasters. The state files stop at the state line,
    which forces a 16-way mosaic, leaves Background padding that biases border
    cells, and fails whenever any one state download fails -- that cost this
    project ten states in 2015 and seven in 2018. One national raster removes all
    of it, and USDA serves it from their own host rather than the GMU service
    that keeps falling over.

    Streams to disk and resumes a partial download, since a 1.9 GB transfer that
    has to restart from zero is its own failure mode.
    """
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / f"CDL_{year}_national.tif"
    if target.exists() and target.stat().st_size > 0:
        return target

    archive = dest / f"{year}_30m_cdls.zip"
    url = NATIONAL_URL.format(year=year)

    head = requests.head(url, timeout=timeout, allow_redirects=True)
    head.raise_for_status()
    expected = int(head.headers.get("Content-Length", 0))

    have = archive.stat().st_size if archive.exists() else 0
    if expected and have == expected:
        pass  # already downloaded in full
    else:
        headers = {"Range": f"bytes={have}-"} if have else {}
        with requests.get(url, stream=True, timeout=timeout, headers=headers) as response:
            response.raise_for_status()
            mode = "ab" if have and response.status_code == 206 else "wb"
            if mode == "wb":
                have = 0
            with open(archive, mode) as handle:
                for block in response.iter_content(chunk_size=chunk):
                    handle.write(block)
        if expected and archive.stat().st_size != expected:
            raise RuntimeError(
                f"{archive.name} is {archive.stat().st_size} bytes, expected {expected}"
            )

    import zipfile

    with zipfile.ZipFile(archive) as bundle:
        tifs = [n for n in bundle.namelist() if n.lower().endswith(".tif")]
        if not tifs:
            raise RuntimeError(f"no .tif inside {archive.name}: {bundle.namelist()[:8]}")
        # Auxiliary files (.tif.aux.xml, .tif.vat.dbf) sit beside the raster.
        main = min(tifs, key=len)
        with bundle.open(main) as src, open(target, "wb") as out:
            while block := src.read(chunk):
                out.write(block)
    archive.unlink(missing_ok=True)
    return target


def download_cdl(year: int, state: str, dest: Path, timeout: int = 300) -> Path:
    """Fetch one state-year CDL GeoTIFF, skipping it if already held."""
    state = state.upper()
    if state not in STATE_FIPS:
        raise ValueError(f"unknown state {state!r}; known: {sorted(STATE_FIPS)}")
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / f"CDL_{year}_{state}.tif"
    if target.exists() and target.stat().st_size > 0:
        return target

    # FIPS must be zero-padded to two digits: the service rejects "9" for
    # Connecticut with "The FIPS Code ... doesn't exist" but accepts "09".
    handshake = requests.get(
        CDL_SERVICE, params={"year": year, "fips": f"{STATE_FIPS[state]:02d}"}, timeout=timeout
    )
    handshake.raise_for_status()
    match = re.search(r"<returnURL>(.*?)</returnURL>", handshake.text)
    if not match:
        raise RuntimeError(f"no returnURL for {state} {year}: {handshake.text[:200]}")

    raster = requests.get(match.group(1), timeout=timeout)
    raster.raise_for_status()
    target.write_bytes(raster.content)
    return target


def download_many(
    years,
    states,
    dest: Path,
    pause: float = 1.0,
    attempts: int = 3,
    backoff: float = 20.0,
) -> dict[str, Path | str]:
    """Fetch a grid of state-years. Returns a path or an error string per key.

    The service times out intermittently -- a build of 2013-2018 lost ten of
    sixteen states for 2015 alone while the same states succeeded in every other
    year -- so each state-year is retried with a widening pause before being
    given up on. Anything already on disk is returned without a request.
    """
    out: dict[str, Path | str] = {}
    for year in years:
        for state in states:
            key = f"{state}_{year}"
            last = ""
            for attempt in range(1, attempts + 1):
                try:
                    out[key] = download_cdl(year, state, dest)
                    time.sleep(pause)
                    break
                except Exception as exc:  # noqa: BLE001 -- recorded, not swallowed
                    last = f"{type(exc).__name__}: {exc}"
                    if attempt < attempts:
                        time.sleep(backoff * attempt)
            else:
                out[key] = f"after {attempts} attempts: {last}"
    return out


def coverage_report(table: pd.DataFrame, column: str = "Forage_spring_1km") -> pd.DataFrame:
    """Scored-cell counts per year, so a short year cannot pass unnoticed.

    A year missing state rasters still produces a full-length table -- the gaps
    are NaN, not absent rows -- so the only way to see the problem is to compare
    the scored count across years.
    """
    summary = (
        table.groupby("year")[column]
        .agg(scored="count", mean="mean")
        .assign(cells=table.groupby("year").size())
    )
    summary["complete"] = summary["scored"] >= 0.95 * summary["scored"].max()
    return summary.round(3)


def _buffers(cells: pd.DataFrame, radius_m: float):
    """Cell centres buffered by ``radius_m``, in the CDL's CRS."""
    import geopandas as gpd
    from shapely.geometry import Point

    points = gpd.GeoDataFrame(
        cells.reset_index(drop=True),
        geometry=[Point(x, y) for x, y in zip(cells["lon"], cells["lat"])],
        crs="EPSG:4326",
    ).to_crs(CDL_CRS)
    buffered = points.copy()
    buffered["geometry"] = points.geometry.buffer(radius_m)
    return buffered


def forage_index(
    rasters,
    cells: pd.DataFrame,
    radii_m=DEFAULT_RADII_M,
    lookup: np.ndarray | None = None,
    background_as_nodata: bool = True,
) -> pd.DataFrame:
    """Area-weighted mean Koh spring index around each cell, at each radius.

    Args:
        rasters: One CDL GeoTIFF path, or several to mosaic. Several are read as
            a virtual mosaic so buffers spanning a state line stay complete.
        cells: Frame with ``col``, ``row``, ``lon``, ``lat``.
        radii_m: Foraging radii in metres.
        lookup: 256-entry class lookup; defaults to the Koh spring index.
        background_as_nodata: CDL class 0 ("Background") is what a state raster
            holds *outside* the state line, and over ocean. Scoring it as zero
            forage treats missing data as barren and drags border cells down
            hard -- in a Delaware test, 288 of 565 cells had >5% Background in
            their 1 km buffer and were understated by 0.158 on average. True
            (the default) excludes Background from the weighted mean and
            renormalises over the remaining area. Interior cells are unaffected,
            so this does not change values away from an edge.

    Returns:
        ``cells`` plus one ``Forage_spring_{n}km`` column per radius. A cell whose
        buffer covers no usable data gets NaN rather than a silent zero.

    Mosaicking the adjoining states is the proper fix for a *state* border;
    renormalising is what remains for a true edge such as a coastline.
    """
    import rasterio
    from exactextract import exact_extract

    lookup = load_koh_lookup() if lookup is None else lookup
    paths = [Path(rasters)] if isinstance(rasters, (str, Path)) else [Path(p) for p in rasters]
    missing = [p for p in paths if not p.exists()]
    if missing:
        raise FileNotFoundError(f"CDL raster(s) not found: {missing}")

    out = cells.reset_index(drop=True).copy()

    # Rasters are accumulated one at a time rather than merged. A 16-state
    # mosaic at 30 m is billions of pixels and will not fit in memory, and it is
    # unnecessary: each state's real data is disjoint from every other's -- they
    # overlap only in the Background padding, which carries no weight. So the
    # area-weighted mean over the union is the sum of each raster's weighted
    # floral area divided by the sum of its scored area.
    for radius in radii_m:
        buffers = _buffers(out, radius)
        floral = np.zeros(len(out), dtype="float64")   # sum of index x area
        scored = np.zeros(len(out), dtype="float64")   # area with a real class
        seen = np.zeros(len(out), dtype=bool)          # any raster covered it

        for path in paths:
            with rasterio.open(path) as source:
                # Only hand this raster the buffers that actually reach it.
                # Without this, every state raster would be extracted against
                # every cell in the region, which is the difference between
                # minutes and days at Northeast extent.
                nearby = _buffers_within(source, buffers)
                if nearby.empty:
                    continue
                stats = exact_extract(
                    source, nearby, ["unique", "frac", "count"],
                    output="pandas", include_geom=False,
                )
                for position, (classes, fractions, count) in zip(
                    nearby.index,
                    zip(stats["unique"], stats["frac"], stats["count"]),
                ):
                    i = int(position)
                    count = float(count)
                    if count <= 0:
                        continue
                    seen[i] = True
                    classes = np.asarray(classes, dtype=int)
                    fractions = np.asarray(fractions, dtype=float) * count
                    usable = (classes >= 0) & (classes < _LUT_SIZE)
                    if background_as_nodata:
                        usable &= classes != 0
                    floral[i] += float(np.sum(lookup[classes[usable]] * fractions[usable]))
                    scored[i] += float(fractions[usable].sum())

        with np.errstate(invalid="ignore", divide="ignore"):
            values = np.where(scored > 0, floral / scored, np.nan)
        values[~seen] = np.nan
        out[f"Forage_spring_{radius // 1000}km"] = values

    return out


def _buffers_within(source, buffers):
    """The subset of ``buffers`` whose bounds overlap this raster's extent.

    Index is preserved, so callers can map results back to the original rows.
    """
    left, bottom, right, top = source.bounds
    bounds = buffers.bounds  # minx, miny, maxx, maxy per geometry
    overlapping = (
        (bounds["maxx"] >= left) & (bounds["minx"] <= right)
        & (bounds["maxy"] >= bottom) & (bounds["miny"] <= top)
    )
    return buffers[overlapping]


def build_forage_table(
    cells: pd.DataFrame,
    years,
    raster_dir: Path,
    states,
    radii_m=DEFAULT_RADII_M,
    progress: bool = True,
) -> pd.DataFrame:
    """Forage index for every cell-year, in the layout ``ForageGrid.load`` reads.

    Expects the CDL rasters for ``states`` and ``years`` to be present in
    ``raster_dir`` already (see :func:`download_many`).
    """
    raster_dir = Path(raster_dir)
    frames = []
    for year in years:
        paths = [raster_dir / f"CDL_{year}_{s.upper()}.tif" for s in states]
        paths = [p for p in paths if p.exists()]
        if not paths:
            if progress:
                print(f"  {year}: no rasters found, skipped", flush=True)
            continue
        frame = forage_index(paths, cells, radii_m=radii_m)
        frame.insert(4, "year", year)
        frames.append(frame)
        if progress:
            done = frame[f"Forage_spring_{radii_m[0] // 1000}km"]
            print(f"  {year}: {done.notna().sum():,}/{len(frame):,} cells "
                  f"(mean {done.mean():.3f})", flush=True)

    if not frames:
        raise FileNotFoundError(f"no CDL rasters found in {raster_dir} for {list(years)}")
    columns = ["lon", "lat", "col", "row", "year"] + [f"Forage_spring_{r // 1000}km" for r in radii_m]
    return pd.concat(frames, ignore_index=True)[columns]
