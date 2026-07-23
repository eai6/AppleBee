"""The AppleBee model: the four sub-models assembled over one bee lifecycle.

Timing for a cohort whose weather year is ``Y`` (Figure 4-1):

1. **Emergence** -- degree-days accumulate from 1 January of ``Y`` until the
   thermal constant is reached (Eq. 4.1).
2. **Egg production** -- the female mates for ``mating_days``, then forages for
   ``longevity - mating_days`` days laying eggs (Eqs. 4.2-4.3).
3. **Egg and larva mortality** -- each egg develops for ``EL`` days from the day
   it was laid (Eqs. 4.4-4.6).
4. **Winter mortality** -- risk accrues over the pre-winter period, 15 August to
   1 October of ``Y`` (Eqs. 4.7-4.8).

The resulting adult offspring per female (Eq. 4.10) is the abundance of the
*following* spring, so a run over weather years 2008-2023 reports reproductive
success for 2009-2024.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from .config import ModelParams
from .forage import ForageGrid
from .submodels import (
    InsufficientWeather,
    egg_larva_mortality,
    egg_production,
    emergence_date,
    reproductive_success,
    winter_mortality,
)
from .weather import WeatherGrid

# Offset applied to the weather year to get the year the offspring are counted.
OFFSPRING_YEAR_OFFSET = 1


@dataclass
class GridYearResult:
    """Full model output for one grid cell in one weather year."""

    col: int
    row: int
    weather_year: int
    offspring_year: int
    emergence_doy: int
    emergence_date: str
    eggs: int
    forage_quality: float
    eggs_per_day: int
    egg_larva_mortality: float
    winter_mortality: float
    offspring: float
    mean_cold_days: float
    mean_hot_days: float
    prewinter_warm_days: int
    no_egg_days_temperature: int
    no_egg_days_precipitation: int


class AppleBee:
    """Runs the AppleBee model over a weather and forage grid."""

    def __init__(
        self,
        tmean: WeatherGrid,
        ppt: WeatherGrid,
        forage: ForageGrid,
        params: ModelParams | None = None,
    ) -> None:
        self.tmean = tmean
        self.ppt = ppt
        self.forage = forage
        self.params = params or ModelParams()

    # -- one cell, one year -------------------------------------------------

    def run_grid_year(self, col: int, row: int, year: int) -> GridYearResult:
        """Run the full lifecycle for one grid cell and weather year."""
        p = self.params

        # 1. Emergence (Eq. 4.1). Degree-days from 1 January.
        jan1 = pd.Timestamp(year=year, month=1, day=1)
        # A whole year of temperature is ample; emergence falls in spring.
        year_temps = self.tmean.year_series(col, row, year)
        emergence = emergence_date(
            year_temps,
            base_temp=p.emergence_base_temp,
            thermal_constant=p.emergence_thermal_constant,
        )
        emergence_ts = jan1 + pd.Timedelta(days=emergence.day_of_year - 1)

        # 2. Egg production (Eqs. 4.2-4.3) over the foraging period.
        foraging_start = emergence_ts + pd.Timedelta(days=p.mating_days)
        foraging_days = p.longevity - p.mating_days
        forage_quality = self.forage.get(col, row, year)
        if forage_quality is None:
            raise KeyError(f"no forage index for grid cell ({col}, {row})")

        eggs = egg_production(
            tmean=self.tmean.series(col, row, foraging_start, foraging_days),
            ppt=self.ppt.series(col, row, foraging_start, foraging_days),
            forage_quality=forage_quality,
            temperature_threshold=p.temperature_threshold,
            precipitation_threshold=p.precipitation_threshold,
            forage_threshold=p.forage_threshold,
            eggs_high_forage=p.eggs_high_forage,
            eggs_low_forage=p.eggs_low_forage,
        )

        # 3. Egg and larva mortality (Eqs. 4.4-4.6). Offsets are relative to the
        #    first day of foraging, and development runs EL days from each egg.
        if eggs.egg_offsets.size:
            span = int(eggs.egg_offsets[-1]) + p.egg_larva_days
            dev_temps = self.tmean.series(col, row, foraging_start, span)
        else:
            dev_temps = np.empty(0, dtype="float32")
        larva = egg_larva_mortality(
            tmean_from_first_egg=dev_temps,
            egg_offsets=eggs.egg_offsets,
            egg_larva_days=p.egg_larva_days,
            mortality_factor=p.mortality_factor,
            lower_dev_threshold=p.lower_dev_threshold,
            upper_dev_threshold=p.upper_dev_threshold,
        )

        # 4. Winter mortality (Eqs. 4.7-4.8) over the pre-winter period.
        sp = pd.Timestamp(year=year, month=p.prewinter_start[0], day=p.prewinter_start[1])
        ep = pd.Timestamp(year=year, month=p.prewinter_end[0], day=p.prewinter_end[1])
        winter = winter_mortality(
            self.tmean.series(col, row, sp, (ep - sp).days),
            diapause_temp_threshold=p.diapause_temp_threshold,
            winter_mortality_factor=p.winter_mortality_factor,
        )

        offspring = reproductive_success(eggs.eggs, larva.mortality, winter.mortality)

        return GridYearResult(
            col=int(col),
            row=int(row),
            weather_year=int(year),
            offspring_year=int(year) + OFFSPRING_YEAR_OFFSET,
            emergence_doy=emergence.day_of_year,
            emergence_date=str(emergence_ts.date()),
            eggs=eggs.eggs,
            forage_quality=eggs.forage_quality,
            eggs_per_day=eggs.eggs_per_day,
            egg_larva_mortality=larva.mortality,
            winter_mortality=winter.mortality,
            offspring=offspring,
            mean_cold_days=larva.mean_cold_days,
            mean_hot_days=larva.mean_hot_days,
            prewinter_warm_days=winter.warm_days,
            no_egg_days_temperature=eggs.no_egg_days_temperature,
            no_egg_days_precipitation=eggs.no_egg_days_precipitation,
        )

    # -- many cells and years ----------------------------------------------

    def run(
        self,
        cells: Iterable[tuple[int, int]],
        years: Iterable[int],
        progress: bool = False,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Run every (cell, year) combination.

        Returns:
            ``(results, failures)`` -- one frame of successful runs and one of
            cell-years that could not be evaluated, with the reason. Failures
            are returned rather than dropped so coverage is always auditable.
        """
        cells = list(cells)
        years = list(years)
        rows: list[dict] = []
        failures: list[dict] = []

        for n, year in enumerate(years, start=1):
            for col, row in cells:
                try:
                    rows.append(asdict(self.run_grid_year(col, row, year)))
                except (InsufficientWeather, KeyError, ValueError) as exc:
                    failures.append(
                        {
                            "col": col,
                            "row": row,
                            "weather_year": year,
                            "error": type(exc).__name__,
                            "message": str(exc),
                        }
                    )
            if progress:
                print(f"  [{n}/{len(years)}] {year}: {len(rows)} ok, {len(failures)} failed", flush=True)

        return pd.DataFrame(rows), pd.DataFrame(failures)
