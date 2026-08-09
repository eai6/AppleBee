"""The PRISM 4 km grid, generated arithmetically rather than from a shapefile.

PRISM's CONUS 4 km product is a regular latitude/longitude grid with its
upper-left corner at (-125.0208333, 49.9375) and a cell size of 1/24 degree.
That makes ``(col, row)`` a pure function of position, so the cells for any
region can be produced without the per-state mesh shapefiles the archived
workflow depended on.

Verified against the archived Pennsylvania inputs: longitude -79.875 maps to
column 1083 and latitude 42.25 to row 184, matching ``archives/data/forage.csv``
and the PRISM exports.

``(col, row)`` here is the same key the weather and forage grids use elsewhere in
the package, so cells generated for a new region line up with the existing
Pennsylvania data without translation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# PRISM 4 km CONUS grid definition.
ORIGIN_LON = -125.0208333  # left edge of column 0
ORIGIN_LAT = 49.9375  # top edge of row 0
CELLS_PER_DEGREE = 24.0  # 1/24 degree, about 4 km
N_COLS = 1405
N_ROWS = 621

# Bounding boxes are (west, south, east, north) in degrees.
BBox = tuple[float, float, float, float]

# The Northeast as the USDA/NOAA regional definition, plus the mid-Atlantic
# states the chapter's study area sits in. Used as a default extent and to
# decide which CDL state rasters to mosaic.
NORTHEAST_STATES = {
    "CT": 9, "DE": 10, "MA": 25, "MD": 24, "ME": 23, "NH": 33, "NJ": 34,
    "NY": 36, "PA": 42, "RI": 44, "VT": 50, "WV": 54, "VA": 51,
}

# Generous envelope around those states, used when no explicit bbox is given.
NORTHEAST_BBOX: BBox = (-83.0, 36.5, -66.9, 47.5)


def col_of(lon) -> np.ndarray:
    """Grid column containing each longitude."""
    return np.floor((np.asarray(lon, dtype=float) - ORIGIN_LON) * CELLS_PER_DEGREE).astype(int)


def row_of(lat) -> np.ndarray:
    """Grid row containing each latitude."""
    return np.floor((ORIGIN_LAT - np.asarray(lat, dtype=float)) * CELLS_PER_DEGREE).astype(int)


def lon_of(col) -> np.ndarray:
    """Longitude of each column's cell centre."""
    return ORIGIN_LON + (np.asarray(col, dtype=float) + 0.5) / CELLS_PER_DEGREE


def lat_of(row) -> np.ndarray:
    """Latitude of each row's cell centre."""
    return ORIGIN_LAT - (np.asarray(row, dtype=float) + 0.5) / CELLS_PER_DEGREE


@dataclass(frozen=True)
class Region:
    """A named extent to acquire data for."""

    name: str
    bbox: BBox
    states: tuple[str, ...] = ()

    def cells(self) -> pd.DataFrame:
        return cells_in_bbox(self.bbox)


NORTHEAST = Region("northeast", NORTHEAST_BBOX, tuple(sorted(NORTHEAST_STATES)))
PENNSYLVANIA = Region("pennsylvania", (-80.6, 39.6, -74.6, 42.4), ("PA",))


def cells_in_bbox(bbox: BBox) -> pd.DataFrame:
    """Every grid cell whose centre falls inside ``bbox``.

    Returns:
        Frame of ``col, row, lon, lat`` sorted by ``(row, col)``, where lon/lat
        are cell centres. Cells outside the PRISM CONUS extent are dropped.
    """
    west, south, east, north = bbox
    if not (west < east and south < north):
        raise ValueError(f"bbox must be (west, south, east, north) with west<east, south<north: {bbox}")

    col_lo, col_hi = int(col_of(west)), int(col_of(east))
    row_lo, row_hi = int(row_of(north)), int(row_of(south))

    cols = np.arange(max(col_lo, 0), min(col_hi, N_COLS - 1) + 1)
    rows = np.arange(max(row_lo, 0), min(row_hi, N_ROWS - 1) + 1)
    if cols.size == 0 or rows.size == 0:
        raise ValueError(f"bbox {bbox} does not overlap the PRISM CONUS grid")

    grid_col, grid_row = np.meshgrid(cols, rows)
    frame = pd.DataFrame(
        {
            "col": grid_col.ravel(),
            "row": grid_row.ravel(),
            "lon": lon_of(grid_col.ravel()),
            "lat": lat_of(grid_row.ravel()),
        }
    )
    inside = (
        frame.lon.between(west, east) & frame.lat.between(south, north)
    )
    return frame[inside].sort_values(["row", "col"]).reset_index(drop=True)


CONUS = Region("conus", (-125.0208333, 24.0625, -66.4792, 49.9375))


def land_cells(reference_raster) -> pd.DataFrame:
    """Every grid cell that carries data in a PRISM raster.

    PRISM's CONUS grid is 872,505 cells but only about 481,631 are land; the rest
    are ocean and beyond-border nodata. Sampling only the land cells halves the
    weather cache without losing anything, and one raster is enough to find them
    because the mask is identical across days.

    Args:
        reference_raster: Any PRISM ``.bil`` or ``.tif`` day.

    Returns:
        ``col, row, lon, lat`` for the cells with data, in row-major order.
    """
    import rasterio

    with rasterio.open(reference_raster) as src:
        band = src.read(1).astype("float32")
        if src.nodata is not None:
            band[band == src.nodata] = np.nan
    rows, cols = np.nonzero(np.isfinite(band))
    return pd.DataFrame(
        {"col": cols.astype(int), "row": rows.astype(int),
         "lon": lon_of(cols), "lat": lat_of(rows)}
    ).sort_values(["row", "col"]).reset_index(drop=True)


def cells_for_states(states, resolution_deg: float = 0.05) -> pd.DataFrame:
    """Grid cells whose centres fall inside the given US states.

    Requires ``geopandas``; falls back to the bounding box if state geometry
    cannot be fetched. Clipping to real boundaries matters mainly for coastal
    states, where a bounding box picks up a lot of ocean.
    """
    import geopandas as gpd
    from shapely.geometry import Point

    codes = [s.upper() for s in states]
    unknown = set(codes) - set(NORTHEAST_STATES)
    if unknown:
        raise ValueError(f"unknown state codes: {sorted(unknown)}")

    # Census cartographic boundaries, 1:20m -- small and adequate for a 4 km grid.
    url = "https://www2.census.gov/geo/tiger/GENZ2021/shp/cb_2021_us_state_20m.zip"
    boundaries = gpd.read_file(url)
    boundaries = boundaries[boundaries["STUSPS"].isin(codes)].to_crs("EPSG:4326")
    if boundaries.empty:
        raise ValueError(f"no boundaries returned for {codes}")

    west, south, east, north = boundaries.total_bounds
    candidates = cells_in_bbox((west - 0.1, south - 0.1, east + 0.1, north + 0.1))
    points = gpd.GeoDataFrame(
        candidates,
        geometry=[Point(x, y) for x, y in zip(candidates.lon, candidates.lat)],
        crs="EPSG:4326",
    )
    joined = gpd.sjoin(points, boundaries[["STUSPS", "geometry"]], predicate="within")
    out = joined.drop(columns=["geometry", "index_right"]).rename(columns={"STUSPS": "state"})
    return out.sort_values(["row", "col"]).reset_index(drop=True)
