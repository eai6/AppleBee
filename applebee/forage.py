"""Spring floral resource quality on the 4 km grid.

Values are the Lonsdorf et al. (2009) index scored from USDA Cropland Data
Layer classes with Koh et al. (2016) expert weights, averaged over a 1 km
radius and joined to the PRISM 4 km grid. The index runs 0-1; the model treats
a cell as forage-abundant when it is at or above ``L_H`` (default 0.5).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


def _open(path):
    """A local path, a URL, or a private ``s3://`` object pandas cannot read."""
    source = str(path)
    if not source.startswith("s3://"):
        return path
    import io

    import boto3

    bucket, _, key = source[5:].partition("/")
    body = boto3.client("s3").get_object(Bucket=bucket, Key=key)["Body"].read()
    return io.BytesIO(body)


@dataclass
class ForageGrid:
    """Spring forage index by (grid cell, year).

    The Cropland Data Layer has a gap for part of Pennsylvania in 2017. Rather
    than silently substituting a constant -- as the archived implementation did,
    falling back through ten neighbour lookups to a hard-coded 0.5 -- a missing
    cell-year falls back to the *nearest available year for the same cell* and
    the substitution is recorded in :attr:`fallbacks`.
    """

    table: pd.DataFrame  # indexed by (col, row, year) -> value
    column: str
    fallbacks: dict[tuple[int, int, int], int]

    @classmethod
    def load(cls, path: Path, column: str = "Forage_spring_1km") -> "ForageGrid":
        frame = pd.read_csv(_open(path))
        if column not in frame.columns:
            raise ValueError(f"{path.name} has no column {column!r}")
        frame = frame[["col", "row", "year", column]].dropna(subset=[column])
        frame = frame.astype({"col": int, "row": int, "year": int})
        table = frame.set_index(["col", "row", "year"])[column].sort_index()
        if table.index.has_duplicates:
            table = table.groupby(level=[0, 1, 2]).mean()
        return cls(table=table.to_frame(name="value"), column=column, fallbacks={})

    def __post_init__(self) -> None:
        self._lookup: dict[tuple[int, int, int], float] = {
            (int(c), int(r), int(y)): float(v)
            for (c, r, y), v in self["value"].items()
        }
        # Years available per cell, for the nearest-year fallback.
        self._years_by_cell: dict[tuple[int, int], np.ndarray] = {}
        for (c, r, y) in self._lookup:
            self._years_by_cell.setdefault((c, r), []).append(y)
        self._years_by_cell = {
            k: np.sort(np.array(v)) for k, v in self._years_by_cell.items()
        }

    def __getitem__(self, key):  # delegate for the constructor above
        return self.table[key]

    def get(self, col: int, row: int, year: int) -> float | None:
        """Spring forage index for a cell-year, or None if the cell is unknown.

        Falls back to the nearest year available for the same cell when that
        specific year is missing, recording the substitution in
        :attr:`fallbacks`.
        """
        key = (int(col), int(row), int(year))
        value = self._lookup.get(key)
        if value is not None:
            return value

        years = self._years_by_cell.get((int(col), int(row)))
        if years is None or len(years) == 0:
            return None
        nearest = int(years[np.argmin(np.abs(years - int(year)))])
        self.fallbacks[key] = nearest
        return self._lookup[(int(col), int(row), nearest)]

    @property
    def cells(self) -> list[tuple[int, int]]:
        return sorted(self._years_by_cell)
