"""Daily PRISM weather on the 4 km grid, held as dense numpy matrices.

The source CSVs are "wide": one row per grid cell, one column per day, with
column names like ``PRISM_tmean_stable_4kmD2_20150501_bil``. Reading them is
slow (the Pennsylvania temperature file is 1.6 GB), so the first load parses the
CSV once and caches a float32 ``.npy`` matrix plus its date index. Subsequent
loads memory-map the cache.

Lookups are then plain integer indexing into ``(n_cells, n_days)`` arrays, which
is what makes a statewide multi-year simulation tractable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .config import CACHE

# Matches the 8-digit date stamp in a PRISM column name.
_DATE_RE = re.compile(r"(\d{8})")

# Columns that identify a grid cell rather than a day of weather.
_ID_COLUMNS = {"", "Unnamed: 0", "col", "row", "lon", "lat", "Site", "sprng__", "grid_id"}

# PRISM releases the same day at increasing levels of quality control: "early"
# within a day, "provisional" within six months, "stable" after final QC. A few
# days appear under two release tags in the Pennsylvania export, so prefer the
# most quality-controlled version rather than whichever column came first.
_VERSION_RANK = {"stable": 3, "provisional": 2, "early": 1}


def _version_rank(column: str) -> int:
    for tag, rank in _VERSION_RANK.items():
        if f"_{tag}_" in column:
            return rank
    return 0


@dataclass
class WeatherGrid:
    """Daily values for one variable over a set of grid cells.

    Attributes:
        values: ``(n_cells, n_days)`` float32 matrix of daily values.
        dates: ``DatetimeIndex`` of length ``n_days``, sorted ascending.
        cells: Frame with one row per grid cell (``col``, ``row``, ``lon``,
            ``lat``, and any passthrough columns such as ``Site``), aligned to
            the rows of ``values``.
    """

    values: np.ndarray
    dates: pd.DatetimeIndex
    cells: pd.DataFrame

    def __post_init__(self) -> None:
        # Row index for a (col, row) grid cell, and column index for a date.
        self._cell_index = {
            (int(c), int(r)): i
            for i, (c, r) in enumerate(zip(self.cells["col"], self.cells["row"]))
        }
        self._first_date = self.dates[0]
        # Dates are contiguous daily in every PRISM export we use; verify, so
        # that day-offset arithmetic below is sound.
        expected = pd.date_range(self.dates[0], self.dates[-1], freq="D")
        self._contiguous = len(expected) == len(self.dates) and (expected == self.dates).all()
        if not self._contiguous:
            self._date_index = {d: i for i, d in enumerate(self.dates)}

    # -- indexing helpers ---------------------------------------------------

    def has_cell(self, col: int, row: int) -> bool:
        return (int(col), int(row)) in self._cell_index

    def cell_row(self, col: int, row: int) -> int:
        """Row offset of grid cell ``(col, row)`` in :attr:`values`."""
        try:
            return self._cell_index[(int(col), int(row))]
        except KeyError:
            raise KeyError(f"grid cell ({col}, {row}) is not in this WeatherGrid") from None

    def date_col(self, date) -> int:
        """Column offset of ``date`` in :attr:`values`."""
        ts = pd.Timestamp(date).normalize()
        if self._contiguous:
            idx = (ts - self._first_date).days
            if not 0 <= idx < len(self.dates):
                raise KeyError(f"{ts.date()} is outside the weather record")
            return idx
        try:
            return self._date_index[ts]
        except KeyError:
            raise KeyError(f"{ts.date()} is outside the weather record") from None

    def series(self, col: int, row: int, start, n_days: int) -> np.ndarray:
        """``n_days`` consecutive daily values from ``start`` for one grid cell.

        Raises KeyError if the window runs past the end of the record, so that a
        truncated window can never be silently mistaken for a complete one.
        """
        i = self.cell_row(col, row)
        j = self.date_col(start)
        end = j + n_days
        if end > self.values.shape[1]:
            raise KeyError(
                f"window {pd.Timestamp(start).date()} +{n_days}d runs past the "
                f"end of the record ({self.dates[-1].date()})"
            )
        return self.values[i, j:end]

    def year_series(self, col: int, row: int, year: int) -> np.ndarray:
        """All daily values in ``year`` for one grid cell."""
        start = pd.Timestamp(year=year, month=1, day=1)
        n = 366 if pd.Timestamp(year=year, month=12, day=31).dayofyear == 366 else 365
        return self.series(col, row, start, n)

    @property
    def n_cells(self) -> int:
        return self.values.shape[0]


def _parse_wide_csv(path: Path) -> tuple[np.ndarray, pd.DatetimeIndex, pd.DataFrame]:
    """Read a wide PRISM CSV into (values, dates, cells)."""
    header = pd.read_csv(path, nrows=0)
    date_cols, dates, id_cols = [], [], []
    for name in header.columns:
        match = _DATE_RE.search(name)
        if match and name not in _ID_COLUMNS:
            date_cols.append(name)
            dates.append(pd.Timestamp(match.group(1)))
        elif name in _ID_COLUMNS or not match:
            id_cols.append(name)

    if not date_cols:
        raise ValueError(f"{path.name} has no recognisable PRISM day columns")

    # Where a date appears more than once, keep the best-quality release.
    best: dict[pd.Timestamp, str] = {}
    for name, date in zip(date_cols, dates):
        incumbent = best.get(date)
        if incumbent is None or _version_rank(name) > _version_rank(incumbent):
            best[date] = name

    date_index = pd.DatetimeIndex(sorted(best))
    ordered_cols = [best[d] for d in date_index]

    frame = pd.read_csv(
        path,
        usecols=id_cols + ordered_cols,
        dtype={c: "float32" for c in ordered_cols},
    )

    values = np.ascontiguousarray(frame[ordered_cols].to_numpy(dtype="float32"))

    keep = [c for c in ("col", "row", "lon", "lat", "Site") if c in frame.columns]
    cells = frame[keep].copy().reset_index(drop=True)
    return values, date_index, cells


def load_matrices(directory: Path, key: str) -> WeatherGrid:
    """Load an already-built ``(n_cells, n_days)`` matrix set from any directory.

    Used for weather that has no wide-CSV source to fall back on -- anything
    fetched by :mod:`applebee.acquire.prism`, where the matrices *are* the
    primary copy rather than a derived cache.
    """
    directory = Path(directory)
    missing = [
        p for p in (directory / f"{key}.values.npy", directory / f"{key}.dates.npy",
                    directory / f"{key}.cells.parquet") if not p.exists()
    ]
    if missing:
        raise FileNotFoundError(f"missing matrix files for {key!r}: {missing}")
    return WeatherGrid(
        values=np.load(directory / f"{key}.values.npy", mmap_mode="r"),
        dates=pd.DatetimeIndex(np.load(directory / f"{key}.dates.npy")),
        cells=pd.read_parquet(directory / f"{key}.cells.parquet"),
    )


def load_pennsylvania(variable: str = "tmean") -> WeatherGrid:
    """The Pennsylvania grid, 7,452 cells x 1990-2024.

    Stored as float32 matrices under ``data/inputs/weather/pennsylvania/`` rather
    than as the 2.45 GB of wide PRISM CSV they were parsed from. Same values,
    a third of the size, and no dependency on ``archives/``.
    """
    from .config import PA_PPT_KEY, PA_TMEAN_KEY, PA_WEATHER_DIR

    keys = {"tmean": PA_TMEAN_KEY, "ppt": PA_PPT_KEY}
    if variable not in keys:
        raise ValueError(f"variable must be 'tmean' or 'ppt', got {variable!r}")
    return load_matrices(PA_WEATHER_DIR, keys[variable])


def load_weather(
    path: Path,
    cache_key: str | None = None,
    use_cache: bool = True,
    cache_dir: Path | None = None,
) -> WeatherGrid:
    """Load a wide PRISM CSV, caching the parsed matrix as ``.npy``.

    Args:
        path: Source CSV.
        cache_key: Basename for the cache files; defaults to the CSV stem.
        use_cache: Set False to bypass and rewrite the cache.
        cache_dir: Where the matrices live; defaults to ``data/cache``. Point
            this elsewhere for matrices that are a primary copy rather than a
            derivative -- ``data/cache`` is safe to delete, and anything
            irreplaceable must not live there.
    """
    path = Path(path)
    key = cache_key or path.stem
    root = Path(cache_dir or CACHE)
    root.mkdir(parents=True, exist_ok=True)
    values_path = root / f"{key}.values.npy"
    dates_path = root / f"{key}.dates.npy"
    cells_path = root / f"{key}.cells.parquet"

    if use_cache and values_path.exists() and dates_path.exists() and cells_path.exists():
        # Rebuild if the source CSV is newer than the cache.
        if min(p.stat().st_mtime for p in (values_path, dates_path, cells_path)) >= path.stat().st_mtime:
            return WeatherGrid(
                values=np.load(values_path, mmap_mode="r"),
                dates=pd.DatetimeIndex(np.load(dates_path)),
                cells=pd.read_parquet(cells_path),
            )

    values, dates, cells = _parse_wide_csv(path)
    np.save(values_path, values)
    np.save(dates_path, dates.to_numpy())
    cells.to_parquet(cells_path)
    return WeatherGrid(values=values, dates=dates, cells=cells)
