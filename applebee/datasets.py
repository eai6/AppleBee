"""Simulation datasets — a region's weather and forage, described in one place.

Before this, every script wired regions up itself: ``load_pennsylvania()`` was
special-cased in :mod:`applebee.weather`, three scripts each carried their own
``REGIONS`` dict of a different shape, and ``config`` grew a pair of constants per
region. Adding a region meant editing four files and remembering which form its
weather was stored in.

A :class:`Dataset` says where a region's inputs are and how they are stored, and
knows how to load them. Everything downstream asks the dataset rather than the
filesystem::

    from applebee.datasets import DATASETS, describe
    print(describe())                      # what is on disk, and its coverage

    model = DATASETS["conus"].model()      # weather + forage + default params
    results, failures = model.run(DATASETS["conus"].cells(), range(2013, 2019))

Weather comes in two forms. Small extents keep the wide PRISM CSV they arrived
as; large ones are float32 matrices, because the Pennsylvania export alone is
2.45 GB of CSV against 716 MB of matrix. The dataset records which, so callers
never need to know.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import config
from .forage import ForageGrid
from .model import AppleBee
from .weather import WeatherGrid, load_matrices, load_weather

# How a region's weather is stored on disk.
MATRICES = "matrices"  # {key}.values.npy + .dates.npy + .cells.parquet
WIDE_CSV = "csv"  # the original PRISM export, one column per day


@dataclass(frozen=True)
class Dataset:
    """One region's simulation inputs.

    Attributes:
        name: Registry key, also used to name outputs.
        weather_dir: Directory holding the weather for this region.
        form: :data:`MATRICES` or :data:`WIDE_CSV`.
        tmean: Cache key (matrices) or filename (CSV) for mean temperature.
        ppt: The same for precipitation.
        forage_csv: Lonsdorf spring index for these cells.
        description: One line, shown by :func:`describe`.
    """

    name: str
    weather_dir: Path
    form: str
    tmean: str
    ppt: str
    forage_csv: Path
    description: str = ""

    # -- availability -------------------------------------------------------

    def paths(self) -> dict[str, Path]:
        """Every file this dataset needs, whether or not it exists."""
        if self.form == MATRICES:
            weather = {f"{v} ({p})": self.weather_dir / f"{k}.{p}"
                       for v, k in (("tmean", self.tmean), ("ppt", self.ppt))
                       for p in ("values.npy", "dates.npy", "cells.parquet")}
        else:
            weather = {"tmean": self.weather_dir / self.tmean,
                       "ppt": self.weather_dir / self.ppt}
        return {**weather, "forage": self.forage_csv}

    def missing(self) -> list[Path]:
        return [p for p in self.paths().values() if not p.exists()]

    @property
    def available(self) -> bool:
        return not self.missing()

    def require(self) -> None:
        """Raise with something actionable if inputs are absent."""
        gaps = self.missing()
        if gaps:
            raise FileNotFoundError(
                f"dataset {self.name!r} is missing {len(gaps)} file(s), first: {gaps[0]}. "
                "See data/inputs/MANIFEST.md, or acquire it with scripts/fetch_prism.py "
                "and scripts/build_forage.py."
            )

    # -- loading ------------------------------------------------------------

    def weather(self) -> tuple[WeatherGrid, WeatherGrid]:
        """``(tmean, ppt)`` for this region."""
        self.require()
        if self.form == MATRICES:
            return (load_matrices(self.weather_dir, self.tmean),
                    load_matrices(self.weather_dir, self.ppt))
        return (load_weather(self.weather_dir / self.tmean, cache_key=f"{self.name}_tmean"),
                load_weather(self.weather_dir / self.ppt, cache_key=f"{self.name}_ppt"))

    def forage(self) -> ForageGrid:
        self.require()
        return ForageGrid.load(self.forage_csv)

    def cells(self) -> list[tuple[int, int]]:
        """Grid cells carrying **both** weather and a forage index.

        The two inputs rarely cover exactly the same cells -- a weather extent may
        include ocean, a forage extent may stop at a coastline -- and running a
        cell that has only one of them fails deep inside the model rather than
        here, so the intersection is taken up front.
        """
        tmean, _ = self.weather()
        have_weather = {(int(c), int(r)) for c, r in zip(tmean.cells["col"], tmean.cells["row"])}
        return [cell for cell in self.forage().cells if cell in have_weather]

    def weather_years(self) -> range:
        """Weather years this dataset can actually run.

        A year needs a full calendar of weather (the emergence search reads from
        1 January) and a forage index. Offspring are reported for year + 1.
        """
        tmean, _ = self.weather()
        forage_years = {int(y) for _, _, y in self.forage().table.index}
        first, last = tmean.dates[0], tmean.dates[-1]
        full = {y for y in range(first.year, last.year + 1)
                if first <= pd.Timestamp(year=y, month=1, day=1)
                and pd.Timestamp(year=y, month=12, day=31) <= last}
        usable = sorted(full & forage_years)
        if not usable:
            raise ValueError(f"{self.name}: no year has both a full weather calendar and forage")
        return range(usable[0], usable[-1] + 1)

    def model(self, params: config.ModelParams | None = None) -> AppleBee:
        """An :class:`~applebee.model.AppleBee` wired to this region."""
        tmean, ppt = self.weather()
        return AppleBee(tmean, ppt, self.forage(), params or config.ModelParams())

    def coverage(self) -> dict:
        """Shape and extent, for reporting. Loads the inputs."""
        tmean, _ = self.weather()
        years = self.weather_years()
        return {"dataset": self.name, "cells": len(self.cells()),
                "weather_cells": tmean.n_cells, "days": len(tmean.dates),
                "from": str(tmean.dates[0].date()), "to": str(tmean.dates[-1].date()),
                "weather_years": f"{years.start}-{years.stop - 1}",
                "offspring_springs": f"{years.start + 1}-{years.stop}"}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

DATASETS: dict[str, Dataset] = {
    "pennsylvania": Dataset(
        name="pennsylvania",
        weather_dir=config.PA_WEATHER_DIR, form=MATRICES,
        tmean=config.PA_TMEAN_KEY, ppt=config.PA_PPT_KEY,
        forage_csv=config.PA_FORAGE_CSV,
        description="the chapter's own extent: 7,452 cells, 1990-2024",
    ),
    "northeast": Dataset(
        name="northeast",
        weather_dir=config.NE_WEATHER_DIR, form=MATRICES,
        tmean=config.NE_TMEAN_KEY, ppt=config.NE_PPT_KEY,
        forage_csv=config.NE_FORAGE_CSV,
        description="13 states, 2013-2018",
    ),
    "conus": Dataset(
        name="conus",
        weather_dir=config.CONUS_WEATHER_DIR, form=MATRICES,
        tmean=config.CONUS_TMEAN_KEY, ppt=config.CONUS_PPT_KEY,
        forage_csv=config.CONUS_FORAGE_CSV,
        description="every land cell of the contiguous United States, 2013-2018",
    ),
}

# New York is deliberately absent: its forage index is per site and per radius,
# not a (col, row, year) grid, so it evaluates the egg-production sub-model
# (applebee.evaluation.centrella) rather than driving a simulation.


def get(name: str) -> Dataset:
    """Look up a dataset, listing the alternatives if the name is wrong."""
    try:
        return DATASETS[name]
    except KeyError:
        raise KeyError(f"unknown dataset {name!r}; available: {sorted(DATASETS)}") from None


def available() -> list[str]:
    """Datasets whose inputs are all present on disk."""
    return [name for name, d in DATASETS.items() if d.available]


def describe() -> pd.DataFrame:
    """What is on disk, and what each dataset covers. Cheap for absent ones."""
    rows = []
    for name, d in DATASETS.items():
        row = {"dataset": name, "available": d.available, "description": d.description}
        if d.available:
            try:
                row.update({k: v for k, v in d.coverage().items() if k != "dataset"})
            except Exception as exc:  # noqa: BLE001 -- reported, not raised
                row["error"] = f"{type(exc).__name__}: {exc}"
        else:
            row["missing"] = len(d.missing())
        rows.append(row)
    return pd.DataFrame(rows)
