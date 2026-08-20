"""What the hosted platform answers, as plain functions.

Framework-free and AWS-free on purpose. A handler's job is to turn HTTP into a
dict and a dict back into HTTP; everything between is here, where it can be
tested, called from a notebook, or run on a laptop with no cloud account.

Three questions, matching the three audiences:

``parameters()``
    What can be changed, what it means, and where its default came from. The
    form is built from this rather than hard-coded in the page.
``evaluate(params)``
    What the paper's two evaluations say **under these parameters** — Objective 2
    on 51 observations from 17 New York orchards, Objective 3 on six annual
    counts from one Pennsylvania site. This is the reviewer's question.
``point(lat, lon, params)``
    What the model predicts at one location. This is the grower's question, and
    it is cheap: one cell is 18 KB of weather, so it costs two ranged reads.

Every answer carries its own caveats as data. The model's whole-model evaluation
rests on six annual counts and is not significant (p = 0.36); a platform that
returned a number without saying so would overstate what the model earned.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import warnings
from functools import lru_cache

import numpy as np
import pandas as pd

from . import datasets
from .config import CACHE, OUTPUTS, ModelParams
from .model import AppleBee

# Presentation metadata for the parameter form: what a field means, its unit,
# where the default came from, and a range wide enough to be interesting without
# being absurd. The values themselves live in ModelParams; this only describes
# them, so the two cannot drift on the numbers that matter.
PARAMETERS = {
    "emergence_base_temp": ("T_base", "degree-day base for spring emergence", "°C",
                            "Adams 2001", 0.0, 15.0),
    "emergence_thermal_constant": ("DD", "accumulated degree-days to emergence", "°C·d",
                                   "Adams 2001", 50.0, 500.0),
    "emergence_start_doy": ("SD", "day of year accumulation begins", "day",
                            "Ahn 2014, Lee 2018", 1, 90),
    "mating_days": ("SF", "days after emergence before nesting starts", "days",
                    "McKinney et al. 2012", 0, 10),
    "longevity": ("EF", "adult female lifespan", "days", "Lee et al. 2016", 5, 60),
    "temperature_threshold": ("T_H", "minimum mean temperature for a foraging day", "°C",
                              "McKinney et al. 2012", 5.0, 25.0),
    "precipitation_threshold": ("P_H", "rainfall that prevents foraging", "mm",
                                "McKinney et al. 2012", 0.0, 20.0),
    "forage_threshold": ("L_H", "floral index above which a cell is forage-abundant",
                         "index", "Lonsdorf 2009 / Koh 2016", 0.0, 1.0),
    "eggs_high_forage": ("", "eggs laid on a suitable day, forage-abundant cell", "eggs",
                         "Centrella et al. 2020", 0, 10),
    "eggs_low_forage": ("", "eggs laid on a suitable day, forage-poor cell", "eggs",
                        "Centrella et al. 2020", 0, 10),
    "egg_larva_days": ("EL", "days from egg to larval development", "days",
                       "Lee et al. 2016", 1, 60),
    "mortality_factor": ("M_F", "larval mortality per unsuitable development day", "rate",
                         "McKinney 2017 / Melone 2024", 0.0, 1.0),
    "lower_dev_threshold": ("LDT", "lower bound of larval development", "°C",
                            "McKinney et al. 2017", 0.0, 20.0),
    "upper_dev_threshold": ("UDT", "upper bound of larval development", "°C",
                            "McKinney et al. 2017", 20.0, 45.0),
    "prewinter_start": ("SP", "pre-wintering period begins", "month, day",
                        "Bosch & Kemp 2010", None, None),
    "prewinter_end": ("EP", "pre-wintering period ends", "month, day",
                      "Sgolastra et al. 2011", None, None),
    "diapause_temp_threshold": ("T_D", "temperature below which diapause proceeds", "°C",
                                "Sgolastra et al. 2011", 5.0, 30.0),
    "winter_mortality_factor": ("W_F", "winter mortality risk per warm pre-winter day",
                                "rate", "Sgolastra 2011 / Bosch 2010", 0.0, 0.05),
}

# Stated on every answer that depends on them. Data, not prose in a template, so
# a client cannot render the number and drop the qualification.
CAVEATS = {
    "objective_3": (
        "The whole-model evaluation rests on six annual counts from a single site. "
        "Tested on those six points the slope is not significant (p = 0.36), so the "
        "fit describes agreement rather than establishing it."
    ),
    "forecast_forage": (
        "The floral resource index comes from the most recent Cropland Data Layer, "
        "which NASS publishes in February for the previous crop year. A run for the "
        "current year therefore uses last year's landscape; year-to-year correlation "
        "is r = 0.992-0.995."
    ),
    "daily_mean_temperature": (
        "Foraging suitability is judged on daily mean temperature, so a cold-morning, "
        "warm-afternoon day counts as unsuitable. Unsuitable days are over-counted "
        "where the diurnal range is wide."
    ),
    "extent": (
        "The model was evaluated in the northeastern United States. Predictions "
        "outside that region are extrapolation."
    ),
}

DEFAULT_REGION = "northeast"

# The grid is 4 km, so the nearest cell to a point inside the region is always
# within a few kilometres. Beyond the first figure the answer is about somewhere
# else and says so; beyond the second it is refused, because returning the
# nearest cell to a point in another country is not a prediction.
FAR_KM = 25.0
TOO_FAR_KM = 500.0

# Offspring per female packs into a uint16 at two decimal places: the regional
# maximum is under 35, and the format's ceiling is 655. Sending float64 instead
# would quadruple a payload whose whole point is that it is small.
PACK_SCALE = 100
PACK_CEILING = 65535

# Region runs are deterministic in (region, years, parameters), so an identical
# request is answered from here rather than recomputed. Most visitors run the
# defaults, which makes this the difference between a platform that costs
# nothing to serve and one that pays for the same 268,536 cell-years repeatedly.
REGION_CACHE = CACHE / "web"

# Set by the deployment. Lambda's own /tmp dies with the container, so a cache
# that is not shared is a cache that never hits: without this, every cold
# container pays the full 39 seconds again.
CACHE_BUCKET_ENV = "APPLEBEE_CACHE_BUCKET"
CACHE_PREFIX = "runs"


# ---------------------------------------------------------------------------
# Cached inputs -- loaded once per process, reused by every warm invocation
# ---------------------------------------------------------------------------


@lru_cache(maxsize=4)
def _region(name: str):
    dataset = datasets.get(name)
    tmean, ppt = dataset.weather()
    return dataset, tmean, ppt, dataset.forage()


@lru_cache(maxsize=4)
def _runnable_cells(name: str) -> pd.DataFrame:
    """Cells carrying both weather and a floral index, with their coordinates."""
    dataset, tmean, _, forage = _region(name)
    have_forage = {cell for cell in forage.cells}
    cells = tmean.cells[["col", "row", "lon", "lat"]].copy()
    keep = [(int(c), int(r)) in have_forage for c, r in zip(cells["col"], cells["row"])]
    return cells[keep].reset_index(drop=True)


@lru_cache(maxsize=4)
def _weather_years(name: str) -> list[int]:
    """The years a region can run. Cached: deriving it re-reads every input."""
    return list(datasets.get(name).weather_years())


@lru_cache(maxsize=4)
def _regional_means(name: str) -> np.ndarray | None:
    """Per-cell six-year mean offspring, for context. None if never simulated."""
    path = OUTPUTS / f"{name}_simulation.parquet"
    if not path.exists():
        return None
    frame = pd.read_parquet(path, columns=["col", "row", "offspring"])
    return frame.groupby(["col", "row"]).offspring.mean().to_numpy()


@lru_cache(maxsize=1)
def _centrella():
    from .evaluation import centrella

    return centrella.load_centrella()


# ---------------------------------------------------------------------------
# Answers
# ---------------------------------------------------------------------------


def parameters() -> dict:
    """The parameter set, its defaults, and what each one means."""
    defaults = ModelParams().to_dict()
    fields = []
    for name, (symbol, description, unit, source, low, high) in PARAMETERS.items():
        fields.append({
            "name": name, "symbol": symbol, "description": description,
            "unit": unit, "source": source, "default": defaults[name],
            "min": low, "max": high,
            "type": "date" if isinstance(defaults[name], list) else "number",
        })
    return {"parameters": fields, "defaults": defaults}


def evaluate(params: ModelParams | dict | None = None, *,
             include_baseline: bool = True) -> dict:
    """Re-run the paper's two evaluations under one parameter set.

    Objective 2 has the replication to identify its variance components -- 51
    observations across 17 sites. Objective 3 does not, and says so.
    """
    params = _as_params(params)
    with warnings.catch_warnings():
        # A singular random-effects covariance is the *finding* in Objective 3,
        # reported in the payload rather than raised as a warning nobody sees.
        warnings.simplefilter("ignore")
        answer = {
            "parameters": params.to_dict(),
            "differences": {k: {"default": was, "used": now}
                            for k, (was, now) in params.differences().items()},
            "objective_2": _objective_2(params),
            "objective_3": _objective_3(params),
            "caveats": [CAVEATS["objective_3"]],
        }
        if include_baseline and params != ModelParams():
            answer["baseline"] = {
                "objective_2": _objective_2(ModelParams()),
                "objective_3": _objective_3(ModelParams()),
            }
    return answer


def point(lat: float, lon: float, params: ModelParams | dict | None = None, *,
          region: str = DEFAULT_REGION, years: list[int] | None = None) -> dict:
    """What the model predicts for one location, year by year.

    The grower's question. One cell's weather is 8,764 contiguous bytes per
    variable, so this costs two ranged reads however large the region is.
    """
    params = _as_params(params)
    dataset, tmean, ppt, forage = _region(region)
    cells = _runnable_cells(region)

    distances = _haversine_km(lat, lon, cells["lat"].to_numpy(), cells["lon"].to_numpy())
    nearest = int(np.argmin(distances))
    distance = float(distances[nearest])
    if distance > TOO_FAR_KM:
        raise ValueError(
            f"({lat}, {lon}) is {distance:,.0f} km from the nearest simulated cell; "
            f"the {region} region does not cover it"
        )
    col, row = int(cells.at[nearest, "col"]), int(cells.at[nearest, "row"])

    # From the cached grids: Dataset.model() would re-open the matrices,
    # which on a warm invocation is the entire cost of the request.
    model = AppleBee(tmean, ppt, forage, params)
    weather_years = list(years) if years else _weather_years(region)
    springs, failures = [], []
    for year in weather_years:
        try:
            result = model.run_grid_year(col, row, year)
        except Exception as exc:  # noqa: BLE001 -- reported per year, not fatal
            failures.append({"weather_year": year, "reason": f"{type(exc).__name__}: {exc}"})
            continue
        springs.append({
            "spring": result.offspring_year,
            "weather_year": result.weather_year,
            "offspring_per_female": round(result.offspring, 2),
            "eggs_per_female": result.eggs,
            "emergence_day_of_year": result.emergence_doy,
            "emergence_date": result.emergence_date,
            "forage_index": round(result.forage_quality, 3),
            "egg_larva_mortality": round(result.egg_larva_mortality, 3),
            "winter_mortality": round(result.winter_mortality, 3),
            "days_lost_to_cold": result.no_egg_days_temperature,
            "days_lost_to_rain": result.no_egg_days_precipitation,
        })

    return {
        "location": {
            "requested": {"lat": lat, "lon": lon},
            "cell": {"col": col, "row": row,
                     "lat": float(cells.at[nearest, "lat"]),
                     "lon": float(cells.at[nearest, "lon"])},
            "distance_km": round(distance, 1),
            "region": region,
            "outside_region": distance > FAR_KM,
        },
        "springs": springs,
        "failures": failures,
        "context": _context(region, springs),
        "parameters": params.to_dict(),
        "caveats": _point_caveats(distance),
    }


def region(params: ModelParams | dict | None = None, *, region: str = DEFAULT_REGION,
           years: list[int] | None = None, block: tuple[int, int] | None = None,
           use_cache: bool = True) -> dict:
    """Every cell in a region, packed small enough to send to a browser.

    ``block`` runs only cells ``start:stop``, which is how the work fans out:
    each worker reads one contiguous run of rows in a single ranged request and
    answers for its own slice. Without it, one process runs the lot — 268,536
    cell-years in about 35 seconds.
    """
    params = _as_params(params)
    weather_years = list(years) if years else _weather_years(region)
    key = _region_key(region, weather_years, params, block)
    if use_cache and block is None:
        cached = _cache_read(key)
        if cached is not None:
            return cached

    _, tmean, ppt, forage = _region(region)
    cells = _runnable_cells(region)
    if block is not None:
        cells = cells.iloc[block[0]:block[1]].reset_index(drop=True)

    model = AppleBee(tmean, ppt, forage, params)
    pairs = list(zip(cells["col"].astype(int), cells["row"].astype(int)))
    results, failures = model.run(pairs, weather_years)

    springs = sorted(results.offspring_year.unique().tolist())
    by_cell = results.pivot_table(index=["col", "row"], columns="offspring_year",
                                  values="offspring")
    order = cells.set_index(["col", "row"]).index
    by_cell = by_cell.reindex(order)

    payload = {
        "region": region, "cells": int(len(cells)), "springs": springs,
        "parameters": params.to_dict(),
        "differences": {k: {"default": was, "used": now}
                        for k, (was, now) in params.differences().items()},
        "encoding": {"lon": "float32", "lat": "float32",
                     "values": "uint16", "scale": PACK_SCALE},
        # The grid step, so a client can draw a cell as a cell rather than
        # guessing a dot size and leaving gaps between the rows.
        "cell_degrees": _grid_step(cells["lat"].to_numpy()),
        "lon": _pack(cells["lon"].to_numpy(), "float32"),
        "lat": _pack(cells["lat"].to_numpy(), "float32"),
        "mean": _pack(by_cell.mean(axis=1).to_numpy()),
        "by_spring": {str(s): _pack(by_cell[s].to_numpy()) for s in springs},
        "summary": {
            "mean": round(float(np.nanmean(by_cell.to_numpy())), 2),
            "max": round(float(np.nanmax(by_cell.to_numpy())), 2),
            "min": round(float(np.nanmin(by_cell.to_numpy())), 2),
            "cell_years": int(len(results)),
            "failures": int(len(failures)),
        },
        "caveats": [CAVEATS["objective_3"], CAVEATS["daily_mean_temperature"],
                    CAVEATS["extent"]],
    }
    if block is None:
        _cache_write(key, payload)
    return payload


# Approving a job spends hours of somebody's fetch quota, so it is gated on a
# token supplied to the deployment. Absent, approval is refused outright rather
# than left open: an unset secret must fail closed.
ADMIN_TOKEN_ENV = "APPLEBEE_ADMIN_TOKEN"


def jobs(state: str | None = None) -> dict:
    """The extension queue. Public, because what is queued is not a secret."""
    from .jobs import JobStore

    return {"jobs": [_job_summary(j) for j in JobStore().list(state)]}


def request_job(kind: str, requested_by: str = "", **parameters) -> dict:
    """Ask for the inputs to be extended. A request, not an instruction."""
    from .jobs import JobStore

    store = JobStore()
    job = store.request(kind, requested_by=requested_by, **parameters)
    return {"job": _job_summary(job), "plan": store.plan(job.id),
            "note": "Requested. An administrator has to approve it before it runs."}


def approve_job(job_id: str, token: str | None = None, by: str = "") -> dict:
    """Approve a queued job. Administrators only."""
    import os

    from .jobs import JobStore

    expected = os.environ.get(ADMIN_TOKEN_ENV)
    if not expected:
        raise PermissionError(
            f"approval is disabled: {ADMIN_TOKEN_ENV} is not set on this deployment"
        )
    if not token or token != expected:
        raise PermissionError("not authorised to approve jobs")
    return {"job": _job_summary(JobStore().approve(job_id, by=by))}


def _job_summary(job) -> dict:
    from .jobs import command

    return {"id": job.id, "kind": job.kind, "state": job.state,
            "parameters": job.parameters, "requested_by": job.requested_by,
            "requested_at": job.requested_at, "note": job.note,
            "command": " ".join(command(job))}


def provenance() -> dict:
    """Where the inputs came from and whether they are still what they were."""
    from . import provenance as prov

    summary = prov.summary()
    return {"inputs": summary.to_dict(orient="records")}


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _pack(values: np.ndarray, dtype: str = "uint16") -> str:
    """Base64 of a compact binary array -- JSON, but not JSON numbers.

    268,536 offspring values are 537 KB packed and several megabytes as text.
    """
    array = np.asarray(values, dtype="float64")
    if dtype == "uint16":
        # A cell that failed to run has no value; 0 is the honest stand-in and
        # the failure count travels in the summary rather than being implied.
        scaled = np.nan_to_num(array, nan=0.0) * PACK_SCALE
        array = np.clip(np.rint(scaled), 0, PACK_CEILING).astype("uint16")
    else:
        array = array.astype(dtype)
    return base64.b64encode(array.tobytes()).decode()


def _grid_step(lats: np.ndarray) -> float:
    """Spacing of the grid in degrees, read off the cells themselves."""
    unique = np.unique(np.round(lats, 6))
    if unique.size < 2:
        return 0.0
    return float(np.median(np.diff(unique)))


def _region_key(region: str, years: list[int], params: ModelParams,
                block: tuple[int, int] | None) -> str:
    digest = hashlib.sha256(json.dumps(
        {"region": region, "years": years, "parameters": params.to_dict(),
         "block": block}, sort_keys=True).encode()).hexdigest()
    return f"{region}-{digest[:16]}"


def _cache_bucket() -> str | None:
    import os

    return os.environ.get(CACHE_BUCKET_ENV)


def _cache_read(key: str) -> dict | None:
    bucket = _cache_bucket()
    if bucket:
        import boto3
        import botocore

        try:
            body = boto3.client("s3").get_object(
                Bucket=bucket, Key=f"{CACHE_PREFIX}/{key}.json")["Body"].read()
        except botocore.exceptions.ClientError:
            return None            # a miss, not a failure
        payload = json.loads(body)
    else:
        path = REGION_CACHE / f"{key}.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text())
    payload["cached"] = True
    return payload


def _cache_write(key: str, payload: dict) -> None:
    bucket = _cache_bucket()
    if bucket:
        import boto3

        boto3.client("s3").put_object(
            Bucket=bucket, Key=f"{CACHE_PREFIX}/{key}.json",
            Body=json.dumps(payload).encode(), ContentType="application/json")
        return
    REGION_CACHE.mkdir(parents=True, exist_ok=True)
    (REGION_CACHE / f"{key}.json").write_text(json.dumps(payload))


def _as_params(params) -> ModelParams:
    if params is None:
        return ModelParams()
    if isinstance(params, ModelParams):
        return params
    return ModelParams.from_dict(params)


def _objective_2(params: ModelParams) -> dict:
    from .evaluation import centrella

    result = centrella.evaluate(params, _centrella())
    fit = result["fit"]
    site_var = float(fit.cov_re.iloc[0, 0])
    return {
        "name": "Egg production sub-model (Centrella et al. 2020)",
        "n": int(len(result["design"])),
        "sites": int(result["design"].Site.nunique()),
        "r2": round(result["r2"], 3),
        "rmse": round(result["rmse"], 2),
        "beta": round(float(fit.params["predicted_eggs"]), 3),
        "se": round(float(fit.bse["predicted_eggs"]), 3),
        "p": float(fit.pvalues["predicted_eggs"]),
        "icc": round(site_var / (site_var + float(fit.scale)), 3),
        "significant": bool(float(fit.pvalues["predicted_eggs"]) < 0.05),
    }


def _objective_3(params: ModelParams) -> dict:
    from scipy import stats

    from .evaluation import turley

    _, tmean, ppt, forage = _region("pennsylvania")
    result = turley.evaluate(AppleBee(tmean, ppt, forage, params))
    design, fit = result["design"], result["fit"]
    # The mixed model's own p is optimistic here: one observation per year makes
    # the variance components non-identifiable. The honest test is the six points.
    ols = stats.linregress(design["predicted"], design["observed"])
    return {
        "name": "Whole model (Turley et al. 2022)",
        "n": int(len(design)),
        "sites": 1,
        "r2": round(result["r2"], 3),
        "rmse": round(result["rmse"], 2),
        "beta": round(float(fit.params["predicted"]), 3),
        "se": round(float(fit.bse["predicted"]), 3),
        "p": float(ols.pvalue),
        "p_basis": "ordinary least squares on the six annual counts",
        "significant": bool(ols.pvalue < 0.05),
    }


def _point_caveats(distance_km: float) -> list[str]:
    caveats = [CAVEATS["objective_3"], CAVEATS["daily_mean_temperature"],
               CAVEATS["extent"]]
    if distance_km > FAR_KM:
        caveats.insert(0, (
            f"The nearest simulated cell is {distance_km:,.0f} km away, so this "
            "describes that cell rather than the location you asked about."
        ))
    return caveats


def _context(region: str, springs: list[dict]) -> dict:
    """Where this location sits against the region, if the region has been run."""
    means = _regional_means(region)
    if means is None or not springs:
        return {}
    here = float(np.mean([s["offspring_per_female"] for s in springs]))
    return {
        "mean_offspring_per_female": round(here, 2),
        "regional_mean": round(float(means.mean()), 2),
        "percentile": round(float((means < here).mean() * 100), 1),
        "regional_cells": int(means.size),
    }


def _haversine_km(lat: float, lon: float, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """Great-circle distance, so "nearest" means nearest rather than nearest in degrees."""
    radius = 6371.0088
    phi1, phi2 = math.radians(lat), np.radians(lats)
    dphi = phi2 - phi1
    dlambda = np.radians(lons - lon)
    a = np.sin(dphi / 2) ** 2 + math.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2) ** 2
    return 2 * radius * np.arcsin(np.sqrt(a))
