"""Model parameters and project paths for the AppleBee model.

Parameter values and their literature sources follow Tables 4-1 to 4-4 of the
AppleBee chapter. Every default here is traceable to the manuscript; nothing is
tuned. Calibrated variants live in :func:`ModelParams.calibrated`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
ARCHIVES = ROOT / "archives"
DATA = ROOT / "data"
INPUTS = DATA / "inputs"
CACHE = DATA / "cache"
OUTPUTS = ROOT / "outputs"
FIGURES = OUTPUTS / "figures"
TABLES = OUTPUTS / "tables"

# Everything the model reads lives under data/inputs/, described file by file in
# data/inputs/MANIFEST.md. Weather is grouped by region; each region holds either
# the source CSVs (small extents) or float32 matrices (large ones).
#
# Pennsylvania is stored as matrices rather than the 2.45 GB of wide PRISM CSV it
# was parsed from. The matrices are the same float32 values -- parsing is lossless
# -- at a third of the size, and they make data/inputs/ self-contained. The CSVs
# remain in archives/output/ for anyone who wants the raw export.
PA_WEATHER_DIR = INPUTS / "weather" / "pennsylvania"
PA_TMEAN_KEY = "pa_tmean"
PA_PPT_KEY = "pa_ppt"
PA_FORAGE_CSV = INPUTS / "forage" / "pa_forage_spring_lonsdorf.csv"

NY_WEATHER_DIR = INPUTS / "weather" / "new_york"
NY_TMEAN_CSV = NY_WEATHER_DIR / "ny_tmean_prism_daily.csv"
NY_PPT_CSV = NY_WEATHER_DIR / "ny_ppt_prism_daily.csv"
NY_FORAGE_CSV = INPUTS / "forage" / "ny_forage_spring_2015_sites.csv"

CENTRELLA_CSV = INPUTS / "observations" / "centrella_2020_ny_orchards.csv"
TURLEY_CSV = INPUTS / "observations" / "turley_2022_pa_blue_vane.csv"

# Northeast inputs fetched by applebee.acquire (2013-2018). The weather here is
# a *primary* copy, not a cache: the PRISM rasters were discarded after sampling,
# so there is nothing local to rebuild it from. It lives outside data/cache/ for
# that reason -- see data/inputs/weather/northeast/PROVENANCE.json.
NE_WEATHER_DIR = INPUTS / "weather" / "northeast"
NE_TMEAN_KEY = "northeast_tmean"
NE_PPT_KEY = "northeast_ppt"
NE_FORAGE_CSV = INPUTS / "forage" / "northeast_forage_spring_lonsdorf.csv"

# CONUS, same acquisition path and same caveat: a primary copy, not a cache.
CONUS_WEATHER_DIR = INPUTS / "weather" / "conus"
CONUS_TMEAN_KEY = "conus_tmean"
CONUS_PPT_KEY = "conus_ppt"
CONUS_FORAGE_CSV = INPUTS / "forage" / "conus_forage_spring_lonsdorf.csv"

# The Adams County, PA monitoring site (Turley et al. 2022). All eight trap
# locations fall inside one 4 km PRISM cell, so the chapter treats them as a
# single site.
MONITORING_SITE_LAT = 39.935226
MONITORING_SITE_LON = -77.254530


@dataclass(frozen=True)
class ModelParams:
    """Parameters for the four AppleBee sub-models.

    Attribute names mirror the symbols used in the chapter; the symbol is given
    in brackets in each comment.
    """

    # --- Emergence date sub-model (Table 4-1, Eq. 4.1) ---
    emergence_base_temp: float = 6.53  # [T_base] degC, Adams 2001
    emergence_thermal_constant: float = 209.0  # [DD] degree-days, Adams 2001
    emergence_start_doy: int = 1  # [SD] 1 January (Ahn 2014, Lee 2018)

    # --- Egg production sub-model (Table 4-2, Eqs. 4.2-4.3) ---
    mating_days: int = 2  # [SF offset] McKinney et al. 2012
    longevity: int = 22  # [EF] days, Lee et al. 2016
    temperature_threshold: float = 13.9  # [T_H] degC, McKinney et al. 2012
    precipitation_threshold: float = 5.0  # [P_H] mm, McKinney et al. 2012
    forage_threshold: float = 0.5  # [L_H] index, Lonsdorf 2009 / Koh 2016
    eggs_high_forage: int = 2  # eggs/day when L_i >= L_H
    eggs_low_forage: int = 1  # eggs/day when L_i <  L_H

    # --- Egg and larva mortality sub-model (Table 4-3, Eqs. 4.4-4.6) ---
    egg_larva_days: int = 18  # [EL] days, Lee et al. 2016
    mortality_factor: float = 0.10  # [M_F] McKinney 2017 / Melone 2024
    lower_dev_threshold: float = 10.0  # [LDT] degC, McKinney et al. 2017
    upper_dev_threshold: float = 30.0  # [UDT] degC, McKinney et al. 2017

    # --- Winter mortality sub-model (Table 4-4, Eqs. 4.7-4.8) ---
    prewinter_start: tuple[int, int] = (8, 15)  # [SP] 15 Aug, Bosch & Kemp 2010
    prewinter_end: tuple[int, int] = (10, 1)  # [EP] 1 Oct, Sgolastra et al. 2011
    diapause_temp_threshold: float = 15.0  # [T_D] degC, Sgolastra et al. 2011
    winter_mortality_factor: float = 0.0025  # [W_F] Sgolastra 2011 / Bosch 2010

    @classmethod
    def calibrated(cls) -> "ModelParams":
        """Egg-production thresholds that maximised R^2 on Centrella et al. (2020).

        Reported in the chapter (Objective 2 results): forage 0.54, temperature
        18.72 degC, precipitation 4.33 mm, giving R^2 = 0.60.
        """
        return cls(
            forage_threshold=0.54,
            temperature_threshold=18.72,
            precipitation_threshold=4.33,
        )

    def with_(self, **kwargs) -> "ModelParams":
        """Return a copy with the given fields replaced."""
        return replace(self, **kwargs)


# Sobol sensitivity ranges (Table 4-5).
SOBOL_PROBLEM = {
    "num_vars": 3,
    "names": ["forage_threshold", "temperature_threshold", "precipitation_threshold"],
    "bounds": [[0.4, 0.6], [10.0, 22.0], [0.0, 10.0]],
}
