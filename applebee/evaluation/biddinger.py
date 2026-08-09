"""Objective 3b: evaluate the whole AppleBee model on the Biddinger database.

The chapter's Objective 3 fits Equation 4.11 on six annual *Osmia* counts from a
single site (Turley et al. 2022) with a random intercept per year -- one
observation per group, so the random effect is not identifiable and its BLUP
absorbs the residuals. See section 2 of ``docs/REPLICATION_NOTES.md``.

This module rebuilds that evaluation on the Biddinger *Osmia* database, which
covers 2007-2025 across 11 PRISM cells rather than 2014-2019 across one. The
gain that matters is spatial: with many years per cell, a random intercept *by
cell* is identifiable.

Two properties of the source shape everything here.

**It is a specimen database, not a survey.** Only bees that were caught are
recorded; there are no zero-catch trap records. A cell-year with no rows may mean
"sampled, caught nothing" or "not sampled", and nothing in the extract
distinguishes them. Trap-level effort records are not available, so effort is
held constant by *restriction* -- one trap type, cells sampled continuously --
rather than modelled away.

**It contains Turley, but only for the species it covers.** Both use the
``DJB YYYY-NNNN`` specimen ID scheme. Once IDs are normalised -- Turley writes ten
of them with a four-digit suffix where this file always uses five -- **all 151 of
Turley's *Osmia* records in the six species here are present, with none missing.**

The extract is **species-filtered**: it holds *bucephala*, *cornifrons*,
*georgica*, *lignaria*, *pumila* and *taurus*, while Turley additionally recorded
*atriventris*, *texana* and *conjuncta* at the same traps. Those three account
for 32 of Turley's 183 records (17%).

That is why :func:`load_specimens` does **not** merge Turley by default. Doing so
would add three extra species for 2014-2019 only -- inflating the count in
exactly the six years the chapter used, and making "genus *Osmia*" mean something
different in those years than in the rest of the series. The response this module
produces is *Osmia* **restricted to the six species the extract covers**,
consistently in every year.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..config import BIDDINGER_XLSX, ModelParams, TURLEY_CSV
from ..model import AppleBee
from .turley import TARGET_GENUS, nearest_cell

BIDDINGER_SHEET = "Edward, Osmia"

# Pennsylvania bounding box, used to reject unparseable or corrupt coordinates.
PA_LAT_RANGE = (39.0, 42.5)
PA_LON_RANGE = (-81.0, -74.0)

# Blue vane. The database switches from pan traps to blue vane around 2012 with
# no overlap, so mixing them would confound trap type with year.
BLUE_VANE = "V"

# Cells sampled by blue vane in essentially every year from 2012. The other six
# blue-vane cells are episodic (2015-2017 or 2012-2014 only) and enter through
# the `cells` argument for sensitivity runs.
CONTINUOUS_CELLS = ((1145, 239), (1146, 239), (1146, 240))

# Forage runs 2008-2023 and weather to 2024-07-01, so offspring years 2009-2024
# are modellable. Blue vane starts in 2012.
DEFAULT_YEARS = range(2012, 2025)


# The six Osmia species this extract covers. Turley additionally recorded
# atriventris, texana and conjuncta at the same traps; see the module docstring.
EXTRACT_SPECIES = ("bucephala", "cornifrons", "georgica", "lignaria", "pumila", "taurus")

# Specimen IDs look like "DJB 2014-03176". Turley writes ten of them with a
# four-digit suffix ("DJB 2014-3176"), so a raw string comparison misses those
# matches and re-appends bees that are already present.
_ID_RE = re.compile(r"^\s*DJB\s+(\d{4})-(\d+)\s*$")


def normalise_id(value) -> str:
    """Canonical specimen ID, zero-padding the suffix to five digits."""
    match = _ID_RE.match(str(value))
    if not match:
        return str(value).strip()
    return f"DJB {match.group(1)}-{int(match.group(2)):05d}"


def _parse_degrees(value) -> float:
    """Coordinate to float. Values are text with a degree suffix: ``39.958620°``."""
    if pd.isna(value):
        return np.nan
    text = str(value).replace("°", "").replace("N", "").replace("W", "").strip()
    try:
        return float(text)
    except ValueError:
        return np.nan


@dataclass
class BiddingerData:
    """Tidy specimen records, one row per bee."""

    specimens: pd.DataFrame
    n_turley_only: int  # Turley records absent from the Biddinger extract
    n_shared: int  # records present in both
    dropped: dict[str, int] = field(default_factory=dict)
    # Specimen IDs carried by more than one row. The extract has one such
    # collision -- DJB 2024-02023 appears as two O. bucephala from different
    # farms on different dates. Both rows are kept, since they are two physical
    # bees with a label clash and dropping either would lose a real record; the
    # collision is surfaced here rather than silently deduplicated.
    duplicate_ids: list[str] = field(default_factory=list)


def load_specimens(merge_turley: bool = False) -> BiddingerData:
    """Load the Biddinger extract.

    Args:
        merge_turley: Add the Turley *Osmia* records this extract lacks. **Off by
            default, and it should normally stay off.** Every Turley record in
            the six species here is already present, so the only thing a merge
            adds is *atriventris*, *texana* and *conjuncta* -- and only for
            2014-2019, since Turley covers no other years. That makes the genus
            count 17% larger in exactly the six years the chapter used than in
            the rest of the series, which is a worse defect than the omission it
            fixes. Set True only to reproduce a Turley-comparable genus count
            within 2014-2019.
    """
    raw = pd.read_excel(BIDDINGER_XLSX, sheet_name=BIDDINGER_SHEET).dropna(how="all")
    dropped: dict[str, int] = {"raw_rows": len(raw)}

    frame = pd.DataFrame(
        {
            "specimen_id": raw["ID"].map(normalise_id),
            "year": pd.to_numeric(raw["Year"], errors="coerce"),
            "genus": raw["genus"].astype(str).str.strip(),
            "species": raw["species"].astype(str).str.strip(),
            "farm": raw["farm"],
            "program": raw["program"],
            "trap_type": raw["trap.type"],
            "date_set": pd.to_datetime(raw["Date set trap"], errors="coerce"),
            "lat": raw["Lat.Block(DD)"].map(_parse_degrees),
            "lon": raw["Long.Block(DD)"].map(_parse_degrees),
            "source": "biddinger",
        }
    )

    # Trap-level coordinates are dirtier than block-level ones -- they contain
    # zeros and at least one sign-flipped longitude -- so they are only a
    # fallback, and the bounding-box check below catches what they get wrong.
    fallback_lat = raw["lat.trap"].map(_parse_degrees)
    fallback_lon = raw["long.trap"].map(_parse_degrees)
    frame["lat"] = frame["lat"].fillna(fallback_lat)
    frame["lon"] = frame["lon"].fillna(fallback_lon)

    if merge_turley:
        turley = pd.read_csv(TURLEY_CSV)
        turley = turley[turley["genus"] == TARGET_GENUS].copy()
        turley["nid"] = turley["ID"].map(normalise_id)
        turley_ids = set(turley["nid"])
        shared = turley_ids & set(frame["specimen_id"])
        missing = turley_ids - set(frame["specimen_id"])

        extra = turley[turley["nid"].isin(missing)]
        addition = pd.DataFrame(
            {
                "specimen_id": extra["nid"],
                "year": pd.to_numeric(extra["year"], errors="coerce"),
                "genus": extra["genus"],
                "species": extra["species"].astype(str).str.strip(),
                "farm": extra["farm"],
                "program": np.nan,
                # Turley et al. is a blue vane study throughout.
                "trap_type": BLUE_VANE,
                "date_set": pd.NaT,
                "lat": pd.to_numeric(extra.get("lat.trap"), errors="coerce"),
                "lon": pd.to_numeric(extra.get("long.trap"), errors="coerce"),
                "source": "turley",
            }
        )
        frame = pd.concat([frame, addition], ignore_index=True)
        n_shared, n_turley_only = len(shared), len(missing)
    else:
        n_shared = n_turley_only = 0

    # Turley rows carry no usable coordinates of their own; all eight of its trap
    # locations sit in one cell, which the Biddinger farms already pin down.
    by_farm = (
        frame.dropna(subset=["lat", "lon"]).groupby("farm")[["lat", "lon"]].first()
    )
    needs = frame["lat"].isna() | frame["lon"].isna()
    filled = frame.loc[needs, "farm"].map(by_farm["lat"])
    frame.loc[needs, "lat"] = frame.loc[needs, "lat"].fillna(filled)
    filled = frame.loc[needs, "farm"].map(by_farm["lon"])
    frame.loc[needs, "lon"] = frame.loc[needs, "lon"].fillna(filled)

    before = len(frame)
    in_pa = (
        frame["lat"].between(*PA_LAT_RANGE)
        & frame["lon"].between(*PA_LON_RANGE)
        & frame["year"].notna()
    )
    dropped["no_usable_location_or_year"] = int((~in_pa).sum())
    frame = frame[in_pa].copy()
    frame["year"] = frame["year"].astype(int)
    dropped["kept"] = len(frame)
    assert dropped["kept"] + dropped["no_usable_location_or_year"] == before

    frame = frame.reset_index(drop=True)
    duplicated = frame["specimen_id"][frame["specimen_id"].duplicated()].unique()

    return BiddingerData(
        specimens=frame,
        n_turley_only=n_turley_only,
        n_shared=n_shared,
        dropped=dropped,
        duplicate_ids=sorted(duplicated),
    )


def assign_cells(specimens: pd.DataFrame, cells: pd.DataFrame) -> pd.DataFrame:
    """Attach the nearest PRISM ``(col, row)`` to each specimen."""
    unique = specimens[["lat", "lon"]].drop_duplicates()
    lookup = {
        (lat, lon): nearest_cell(cells, lat, lon)
        for lat, lon in unique.itertuples(index=False)
    }
    assigned = specimens.copy()
    pairs = [lookup[(lat, lon)] for lat, lon in zip(assigned["lat"], assigned["lon"])]
    assigned["col"] = [c for c, _ in pairs]
    assigned["row"] = [r for _, r in pairs]
    return assigned


def build_panel(
    specimens: pd.DataFrame,
    species: str | None = None,
    trap_type: str | None = BLUE_VANE,
    cells: tuple[tuple[int, int], ...] | None = CONTINUOUS_CELLS,
    years: range = DEFAULT_YEARS,
    drop_ambiguous_zeros: bool = True,
) -> pd.DataFrame:
    """Cell-year counts, restricted so that sampling effort is roughly constant.

    Args:
        species: Restrict to one species (e.g. ``"cornifrons"``). None keeps the
            whole *Osmia* genus, which is what the chapter counts.
        trap_type: Restrict to one trap type. None keeps all, which confounds
            trap type with year across the 2012 pan-to-blue-vane switch.
        cells: Restrict to these ``(col, row)`` cells. None keeps all.
        years: Observation years to build the panel over.
        drop_ambiguous_zeros: A cell-year with no records may mean "not sampled"
            rather than "sampled, caught nothing", and the source cannot tell
            them apart. True drops them; False keeps them as genuine zeros.

    Returns:
        One row per (col, row, year) with the count and the effort columns the
        restriction was based on, so a later effort table can be joined in.
    """
    frame = specimens
    if trap_type is not None:
        frame = frame[frame["trap_type"] == trap_type]
    if species is not None:
        frame = frame[frame["species"] == species]
    if cells is not None:
        keys = set(cells)
        frame = frame[[(c, r) in keys for c, r in zip(frame["col"], frame["row"])]]
    frame = frame[frame["year"].isin(list(years))]

    grid_cells = cells if cells is not None else tuple(
        sorted(set(zip(specimens["col"], specimens["row"])))
    )
    index = pd.MultiIndex.from_product(
        [grid_cells, list(years)], names=["cell", "year"]
    )
    counts = (
        frame.groupby([list(zip(frame["col"], frame["row"])), "year"])
        .size()
        .reindex(index, fill_value=0)
        .rename("observed")
        .reset_index()
    )
    counts["col"] = [c for c, _ in counts["cell"]]
    counts["row"] = [r for _, r in counts["cell"]]

    # "Sampled" is judged from the whole genus at that cell-year before any
    # species filter -- a year with pumila but no cornifrons was still sampled.
    sampled = specimens
    if trap_type is not None:
        sampled = sampled[sampled["trap_type"] == trap_type]
    seen = set(zip(sampled["col"], sampled["row"], sampled["year"]))
    counts["sampled"] = [
        (c, r, y) in seen for c, r, y in zip(counts["col"], counts["row"], counts["year"])
    ]

    if drop_ambiguous_zeros:
        counts = counts[counts["sampled"]]

    return counts.drop(columns="cell").reset_index(drop=True)


def build_design(model: AppleBee, panel: pd.DataFrame) -> pd.DataFrame:
    """Join observed cell-year counts to AppleBee predictions.

    Adults counted in spring ``Y`` were produced in weather year ``Y - 1``, per
    ``model.OFFSPRING_YEAR_OFFSET``.
    """
    rows = []
    for entry in panel.itertuples():
        try:
            result = model.run_grid_year(entry.col, entry.row, entry.year - 1)
        except Exception as exc:  # noqa: BLE001 -- recorded, not swallowed
            rows.append({"col": entry.col, "row": entry.row, "year": entry.year,
                         "error": f"{type(exc).__name__}: {exc}"})
            continue
        rows.append(
            {
                "col": entry.col,
                "row": entry.row,
                "year": entry.year,
                "observed": entry.observed,
                "predicted": result.offspring,
                "eggs": result.eggs,
                "emergence_doy": result.emergence_doy,
                "forage_quality": result.forage_quality,
                "egg_larva_mortality": result.egg_larva_mortality,
                "winter_mortality": result.winter_mortality,
                "error": None,
            }
        )
    design = pd.DataFrame(rows)
    failures = design[design["error"].notna()]
    design = design[design["error"].isna()].drop(columns="error").reset_index(drop=True)
    design.attrs["failures"] = failures
    design["cell"] = [f"{c}_{r}" for c, r in zip(design["col"], design["row"])]
    return design


def fit_lme(design: pd.DataFrame):
    """``observed ~ predicted`` with a random intercept **by cell**.

    By cell, not by year: the cells here carry many years each, so the random
    effect is identifiable. The chapter's year effect had one observation per
    group and merely absorbed the residuals.
    """
    import statsmodels.formula.api as smf

    return smf.mixedlm("observed ~ predicted", data=design, groups=design["cell"]).fit(
        method="lbfgs"
    )


def fit_negbin(design: pd.DataFrame):
    """Negative binomial GLM, for a response that is an overdispersed count.

    A Gaussian fit to counts spanning 0-60 is not defensible on its own, so this
    is reported alongside. Cell enters as a fixed factor rather than a random
    one, which statsmodels cannot fit for a negative binomial GLMM.
    """
    import statsmodels.formula.api as smf

    return smf.negativebinomial("observed ~ predicted + C(cell)", data=design).fit(
        disp=False
    )


def r2_marginal_conditional(design: pd.DataFrame, fit) -> dict:
    """Both R^2 for a fitted mixed model, never one without the other.

    Marginal uses fixed effects alone -- what the model explains. Conditional
    adds the random intercepts, and is what the chapter reports. Quoting only
    the conditional value is the flaw this whole module exists to fix.
    """
    observed = design["observed"].to_numpy(float)
    fixed = fit.params["Intercept"] + fit.params["predicted"] * design["predicted"]
    ss_tot = float(((observed - observed.mean()) ** 2).sum())

    def r2(predicted) -> float:
        return 1.0 - float(((observed - np.asarray(predicted, float)) ** 2).sum()) / ss_tot

    return {
        "marginal_r2": r2(fixed),
        "conditional_r2": r2(fit.fittedvalues),
        "rmse": float(np.sqrt(((observed - fit.fittedvalues) ** 2).mean())),
        "slope": float(fit.params["predicted"]),
        "slope_p": float(fit.pvalues["predicted"]),
        "n": int(len(design)),
        "n_cells": int(design["cell"].nunique()),
    }


def evaluate(model: AppleBee, panel: pd.DataFrame) -> dict:
    """Full Objective 3b evaluation for one panel."""
    design = build_design(model, panel)
    fit = fit_lme(design)
    result = r2_marginal_conditional(design, fit)
    result["design"] = design
    result["fit"] = fit
    return result
