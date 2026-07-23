"""Objective 2: evaluate the egg-production sub-model on Centrella et al. (2020).

Seventeen apple orchards in the Finger Lakes region of New York were each
stocked with *O. cornifrons* source nest tubes on 5 May 2015; bees began
emerging on 7 May. Completed nest tubes were collected every six days from
7 May to 24 June, giving 51 observations (17 sites x 3 time points) of eggs
produced per site per six-day window.

Emergence is *observed* here (7 May 2015) rather than predicted, so this
isolates the egg-production sub-model from the emergence sub-model.

The sub-model predicts eggs per female; the observed counts are per site across
roughly 100 stocked bees. The chapter therefore evaluates the sub-model as a
*hybrid* model -- a linear mixed-effects model regresses observed site totals on
the sub-model's prediction (Eq. 4.9), with time point as a fixed effect and site
as a random intercept.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..config import (
    CENTRELLA_CSV,
    ModelParams,
    NY_FORAGE_CSV,
    NY_PPT_CSV,
    NY_TMEAN_CSV,
)
from ..submodels import egg_production
from ..weather import load_weather

# The study's own timeline (Centrella et al. 2020).
EMERGENCE_DATE = pd.Timestamp("2015-05-07")
COLLECTION_INTERVAL_DAYS = 6
N_TIME_POINTS = 3

# Foraging radius for the site-level spring floral resource index. Matches the
# Forage_spring_1km index used for the Pennsylvania grid.
FORAGE_RADIUS = "1km"


@dataclass
class CentrellaData:
    observations: pd.DataFrame  # Site, Time_Point, observed_eggs
    sites: pd.DataFrame  # Site, col, row, forage_quality
    tmean: object
    ppt: object


# The chapter reports observed six-day egg totals with max/mean/min/sd of
# 206/65/12/42. Neither quantity below reproduces those figures: the archived
# Centrella extract carries only *emerged adults* (175/46/4/38) and a larval
# mortality proportion, not the raw brood-cell counts the chapter describes
# counting from the nest tubes. Back-correcting for larval mortality gets to
# 182/52/4/41, still short. The raw egg counts appear to live in a fuller
# version of the Centrella et al. (2020) dataset that is not in this repository,
# so absolute egg totals here are an estimate; see docs/REPLICATION_NOTES.md.
OBSERVED_EGG_DEFINITIONS = ("emerged_adults", "eggs_backcorrected")


def load_centrella(observed_eggs: str = "eggs_backcorrected") -> CentrellaData:
    """Load the New York evaluation dataset and its matching weather grid.

    Args:
        observed_eggs: Which column to treat as the observed response --
            ``emerged_adults`` (what the archive literally records) or
            ``eggs_backcorrected`` (adults corrected for larval mortality).
    """
    if observed_eggs not in OBSERVED_EGG_DEFINITIONS:
        raise ValueError(
            f"observed_eggs must be one of {OBSERVED_EGG_DEFINITIONS}, got {observed_eggs!r}"
        )
    raw = pd.read_csv(CENTRELLA_CSV, encoding="utf-8-sig")

    observations = raw[
        [
            "Site_Code",
            "Time_Point",
            "Calendar_Date",
            "Total_Emerged_Males",
            "Total_Emerged_Females",
            "Proportion_Larval_Mortality",
        ]
    ].copy()
    observations.columns = [
        "Site",
        "Time_Point",
        "collection_date",
        "males",
        "females",
        "larval_mortality",
    ]
    observations["collection_date"] = pd.to_datetime(
        observations["collection_date"], format="%m/%d/%y"
    )
    observations["emerged_adults"] = observations["males"] + observations["females"]
    # Back-correct emerged adults for larval mortality to estimate eggs laid.
    # See OBSERVED_EGG_DEFINITIONS for why this is an estimate.
    observations["eggs_backcorrected"] = observations["emerged_adults"] / (
        1.0 - observations["larval_mortality"]
    )
    observations["observed_eggs"] = observations[observed_eggs]

    tmean = load_weather(NY_TMEAN_CSV, cache_key="ny_tmean")
    ppt = load_weather(NY_PPT_CSV, cache_key="ny_ppt")

    # Site-level spring forage index. The file carries 1 km, 3 km and 5 km
    # radii; use 1 km to match the Forage_spring_1km index used statewide.
    forage = pd.read_csv(NY_FORAGE_CSV)
    forage = forage[(forage["radius"] == FORAGE_RADIUS) & (forage["season"] == "spring")]
    forage = forage[["Site", "value"]].rename(columns={"value": "forage_quality"})
    if forage["Site"].duplicated().any():
        raise ValueError(f"forage index is not unique per site at radius {FORAGE_RADIUS}")

    sites = tmean.cells[["Site", "col", "row"]].merge(forage, on="Site", how="left")
    if sites["forage_quality"].isna().any():
        missing = sites.loc[sites["forage_quality"].isna(), "Site"].tolist()
        raise ValueError(f"no forage index for sites: {missing}")

    return CentrellaData(observations=observations, sites=sites, tmean=tmean, ppt=ppt)


def predict_eggs(data: CentrellaData, params: ModelParams) -> pd.DataFrame:
    """Predict eggs per female for each site and collection window.

    Nest tubes were retrieved and replaced roughly every six days, but the
    recorded collection dates are not perfectly regular across sites, so each
    window is taken as the ``COLLECTION_INTERVAL_DAYS`` ending on that site's
    own recorded collection date. Windows are additionally clipped to start no
    earlier than the day foraging began (emergence plus mating days).
    """
    geometry = data.sites.set_index("Site")
    foraging_start = EMERGENCE_DATE + pd.Timedelta(days=params.mating_days)

    rows = []
    for obs in data.observations.itertuples():
        site = geometry.loc[obs.Site]
        end = obs.collection_date
        start = max(end - pd.Timedelta(days=COLLECTION_INTERVAL_DAYS), foraging_start)
        n_days = (end - start).days
        if n_days <= 0:
            raise ValueError(f"empty collection window for {obs.Site} t{obs.Time_Point}")

        result = egg_production(
            tmean=data.tmean.series(site.col, site.row, start, n_days),
            ppt=data.ppt.series(site.col, site.row, start, n_days),
            forage_quality=site.forage_quality,
            temperature_threshold=params.temperature_threshold,
            precipitation_threshold=params.precipitation_threshold,
            forage_threshold=params.forage_threshold,
            eggs_high_forage=params.eggs_high_forage,
            eggs_low_forage=params.eggs_low_forage,
        )
        rows.append(
            {
                "Site": obs.Site,
                "Time_Point": obs.Time_Point,
                "window_start": start,
                "window_days": n_days,
                "predicted_eggs": result.eggs,
                "forage_quality": site.forage_quality,
                "foraging_days": result.foraging_days,
            }
        )
    return pd.DataFrame(rows)


def build_design(data: CentrellaData, params: ModelParams) -> pd.DataFrame:
    """Join observed counts to predictions, ready for the mixed-effects fit."""
    predictions = predict_eggs(data, params)
    merged = data.observations.merge(predictions, on=["Site", "Time_Point"], how="inner")
    if len(merged) != len(data.observations):
        raise ValueError(
            f"lost observations in the join: {len(data.observations)} -> {len(merged)}"
        )
    return merged


def fit_lme(design: pd.DataFrame):
    """Fit Equation 4.9: observed ~ predicted + time point, random intercept by site.

    Returns the fitted statsmodels result. R^2 is computed by the caller from
    the fitted values, matching how the chapter reports it.
    """
    import statsmodels.formula.api as smf

    model = smf.mixedlm(
        "observed_eggs ~ predicted_eggs + C(Time_Point)",
        data=design,
        groups=design["Site"],
    )
    return model.fit(method="lbfgs")


def r2_and_rmse(observed: np.ndarray, fitted: np.ndarray) -> tuple[float, float]:
    """Marginal-plus-conditional R^2 and RMSE from a fitted mixed model."""
    observed = np.asarray(observed, dtype=float)
    fitted = np.asarray(fitted, dtype=float)
    ss_res = float(((observed - fitted) ** 2).sum())
    ss_tot = float(((observed - observed.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    rmse = float(np.sqrt(((observed - fitted) ** 2).mean()))
    return r2, rmse


def evaluate(params: ModelParams, data: CentrellaData | None = None) -> dict:
    """Full Objective 2 evaluation for one parameter set."""
    data = data if data is not None else load_centrella()
    design = build_design(data, params)
    fit = fit_lme(design)
    r2, rmse = r2_and_rmse(design["observed_eggs"], fit.fittedvalues)
    return {"design": design, "fit": fit, "r2": r2, "rmse": rmse}
