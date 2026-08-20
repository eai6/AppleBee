"""Objective 3: evaluate the whole AppleBee model on Turley et al. (2022).

Solitary bees were monitored with Blue Vane traps at eight locations around the
Pennsylvania State Fruit Research and Extension Center in Adams County, PA,
weekly from April to October, 2014-2019. All eight traps fall within one 4 km
PRISM cell, so the chapter treats them as a single site.

The response is the annual count of bees in the genus *Osmia* (the chapter uses
the genus rather than *O. cornifrons* alone, because cornifrons records are
sparse). The predictor is AppleBee's adult offspring per female. Because
offspring produced in weather year Y are the adults counted in spring Y+1, the
prediction for observation year Y comes from weather year Y-1.

Equation 4.11 fits ``observed ~ predicted`` with a random intercept for year.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import (
    MONITORING_SITE_LAT,
    MONITORING_SITE_LON,
    ModelParams,
    TURLEY_CSV,
)
from ..model import AppleBee

MONITORING_YEARS = range(2014, 2020)
TARGET_GENUS = "Osmia"


def load_osmia_counts(years: range = MONITORING_YEARS) -> pd.DataFrame:
    """Annual counts of Osmia specimens at the Adams County monitoring site."""
    raw = pd.read_csv(TURLEY_CSV)
    osmia = raw[raw["genus"] == TARGET_GENUS]
    counts = (
        osmia.groupby("year").size().reindex(years, fill_value=0).rename("observed").reset_index()
    )
    return counts


def nearest_cell(cells: pd.DataFrame, lat: float, lon: float) -> tuple[int, int]:
    """The (col, row) of the grid cell whose centroid is nearest a point.

    Uses squared degree distance with a cosine correction on longitude, which is
    accurate enough to pick a cell on a 4 km grid at this latitude.
    """
    dlat = cells["lat"].to_numpy() - lat
    dlon = (cells["lon"].to_numpy() - lon) * np.cos(np.radians(lat))
    idx = int(np.argmin(dlat**2 + dlon**2))
    return int(cells.iloc[idx]["col"]), int(cells.iloc[idx]["row"])


def build_design(
    model: AppleBee,
    years: range = MONITORING_YEARS,
    lat: float = MONITORING_SITE_LAT,
    lon: float = MONITORING_SITE_LON,
) -> pd.DataFrame:
    """Join observed Osmia counts to AppleBee predictions for the site."""
    col, row = nearest_cell(model.tmean.cells, lat, lon)

    predictions = []
    for year in years:
        # Adults counted in spring `year` were produced in `year - 1`.
        result = model.run_grid_year(col, row, year - 1)
        predictions.append(
            {
                "year": year,
                "predicted": result.offspring,
                "eggs": result.eggs,
                "egg_larva_mortality": result.egg_larva_mortality,
                "winter_mortality": result.winter_mortality,
                "emergence_doy": result.emergence_doy,
                "forage_quality": result.forage_quality,
            }
        )

    design = load_osmia_counts(years).merge(pd.DataFrame(predictions), on="year", how="inner")
    design.attrs["cell"] = (col, row)
    return design


# One observation per group makes the covariance singular, which leaves this fit
# sitting on the edge of what the optimiser can do: the same data converges with
# a warning on macOS's Accelerate and raises "Singular matrix" on Linux's
# OpenBLAS. The degeneracy is the finding -- it is why the manuscript reports the
# slope as not significant -- but it should not depend on which machine ran it,
# so the optimisers are tried in order rather than trusting one.
OPTIMISERS = ("lbfgs", "bfgs", "cg", "powell")


def fit_lme(design: pd.DataFrame):
    """Fit Equation 4.11: observed ~ predicted, random intercept by year."""
    import statsmodels.formula.api as smf

    frame = design.copy()
    frame["year_group"] = frame["year"].astype(str)
    model = smf.mixedlm("observed ~ predicted", data=frame, groups=frame["year_group"])

    failures = []
    for method in OPTIMISERS:
        try:
            return model.fit(method=method)
        except Exception as exc:  # noqa: BLE001 -- tried in turn, reported together
            failures.append(f"{method}: {type(exc).__name__}: {exc}")
    raise RuntimeError(
        "the mixed model could not be fitted by any optimiser, which is what a "
        "singular random-effects covariance looks like when it stops being "
        "merely a warning:\n  " + "\n  ".join(failures)
    )


def evaluate(model: AppleBee, years: range = MONITORING_YEARS) -> dict:
    """Full Objective 3 evaluation."""
    from .centrella import r2_and_rmse

    design = build_design(model, years)
    fit = fit_lme(design)
    r2, rmse = r2_and_rmse(design["observed"], fit.fittedvalues)
    return {"design": design, "fit": fit, "r2": r2, "rmse": rmse}
