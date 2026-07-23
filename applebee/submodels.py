"""The four AppleBee sub-models, written directly from Equations 4.1-4.8.

Each function is pure: it takes daily weather already extracted for one grid
cell and returns a small result object. Nothing here touches the filesystem or
a DataFrame, which keeps the equations readable and directly testable against
the chapter.

Sub-models and their equations:

===========================  ==========  =============================
Sub-model                    Equations   Entry point
===========================  ==========  =============================
Emergence date               4.1         :func:`emergence_date`
Egg production               4.2, 4.3    :func:`egg_production`
Egg and larva mortality      4.4-4.6     :func:`egg_larva_mortality`
Winter mortality             4.7, 4.8    :func:`winter_mortality`
Reproductive success         4.10        :func:`reproductive_success`
===========================  ==========  =============================
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


class InsufficientWeather(Exception):
    """Raised when the weather record is too short to evaluate a sub-model."""


# ---------------------------------------------------------------------------
# Emergence date -- Equation 4.1
# ---------------------------------------------------------------------------


@dataclass
class EmergenceResult:
    day_of_year: int  # 1-based; 1 == 1 January
    cumulative_degree_days: float


def emergence_date(
    tmean: np.ndarray,
    base_temp: float,
    thermal_constant: float,
) -> EmergenceResult:
    """Day of year on which cumulative degree-days reach the thermal constant.

    Equation 4.1: ``CDD = sum_{i=SD}^{ED} (T_air,i - T_base)``, accumulating only
    the days warm enough to advance development. The emergence date ED is the
    first day on which CDD *equals or exceeds* the thermal constant DD.

    Args:
        tmean: Daily mean temperature (degC) from 1 January of the year.
        base_temp: [T_base] threshold above which development accrues.
        thermal_constant: [DD] degree-days required for emergence.

    Returns:
        EmergenceResult with a 1-based day of year.
    """
    contribution = np.clip(tmean - base_temp, 0.0, None)
    cumulative = np.cumsum(contribution)
    reached = np.flatnonzero(cumulative >= thermal_constant)
    if reached.size == 0:
        raise InsufficientWeather(
            f"cumulative degree-days reached {cumulative[-1]:.1f} of "
            f"{thermal_constant} required over {len(tmean)} days"
        )
    index = int(reached[0])
    # Index 0 is 1 January, so day-of-year is index + 1.
    return EmergenceResult(
        day_of_year=index + 1,
        cumulative_degree_days=float(cumulative[index]),
    )


# ---------------------------------------------------------------------------
# Egg production -- Equations 4.2 and 4.3
# ---------------------------------------------------------------------------


@dataclass
class EggProductionResult:
    eggs: int
    egg_offsets: np.ndarray  # day offsets from start of foraging with an egg laid
    eggs_per_day: int  # 2 where forage is abundant, else 1
    forage_quality: float
    foraging_days: int
    no_egg_days: int
    no_egg_days_temperature: int  # days blocked by T_air,i < T_H
    no_egg_days_precipitation: int  # days blocked by P_i > P_H


def egg_production(
    tmean: np.ndarray,
    ppt: np.ndarray,
    forage_quality: float,
    temperature_threshold: float,
    precipitation_threshold: float,
    forage_threshold: float,
    eggs_high_forage: int = 2,
    eggs_low_forage: int = 1,
) -> EggProductionResult:
    """Eggs laid by one female over her foraging lifetime.

    Equation 4.2 sums a daily step function (Equation 4.3) over the foraging
    period. A day is favourable when ``T_air,i >= T_H`` and ``P_i <= P_H``; on a
    favourable day the female lays 2 eggs where ``L_i >= L_H`` and 1 otherwise.

    Args:
        tmean: Daily mean temperature (degC) over the foraging period.
        ppt: Daily cumulative precipitation (mm), same length as ``tmean``.
        forage_quality: [L_i] spring floral resource index (0-1) at the cell.
        temperature_threshold: [T_H] degC.
        precipitation_threshold: [P_H] mm.
        forage_threshold: [L_H] index.
    """
    if len(tmean) != len(ppt):
        raise ValueError("temperature and precipitation windows must be the same length")

    warm_enough = tmean >= temperature_threshold
    dry_enough = ppt <= precipitation_threshold
    favourable = warm_enough & dry_enough

    eggs_per_day = eggs_high_forage if forage_quality >= forage_threshold else eggs_low_forage
    offsets = np.flatnonzero(favourable)

    return EggProductionResult(
        eggs=int(offsets.size * eggs_per_day),
        egg_offsets=offsets,
        eggs_per_day=eggs_per_day,
        forage_quality=float(forage_quality),
        foraging_days=int(favourable.sum()),
        no_egg_days=int((~favourable).sum()),
        # Attributed independently: a day can be blocked by both drivers, which
        # is how the chapter counts them for the no-egg-day comparison.
        no_egg_days_temperature=int((~warm_enough).sum()),
        no_egg_days_precipitation=int((~dry_enough).sum()),
    )


# ---------------------------------------------------------------------------
# Egg and larva mortality -- Equations 4.4 to 4.6
# ---------------------------------------------------------------------------


@dataclass
class EggLarvaMortalityResult:
    mortality: float  # [M] mean risk across eggs, clipped to [0, 1]
    mean_cold_days: float
    mean_hot_days: float
    n_eggs: int


def egg_larva_mortality(
    tmean_from_first_egg: np.ndarray,
    egg_offsets: np.ndarray,
    egg_larva_days: int,
    mortality_factor: float,
    lower_dev_threshold: float,
    upper_dev_threshold: float,
) -> EggLarvaMortalityResult:
    """Mean mortality risk across the eggs laid at a location.

    Equation 4.5 gives one egg's risk as the count of development days spent
    outside the thermal window ``[LDT, UDT]``, times the mortality factor M_F.
    Equation 4.4 averages that risk over all eggs laid. Per-egg risk is capped
    at 1 before averaging, since a risk is a probability.

    Args:
        tmean_from_first_egg: Daily mean temperature starting on the day the
            *first* egg was laid, long enough to cover the last egg's
            development window.
        egg_offsets: Day offsets of egg-laying relative to that same first day.
        egg_larva_days: [EL] development days, 18.
        mortality_factor: [M_F] risk added per day outside the window.
        lower_dev_threshold: [LDT] degC.
        upper_dev_threshold: [UDT] degC.
    """
    if egg_offsets.size == 0:
        return EggLarvaMortalityResult(0.0, 0.0, 0.0, 0)

    required = int(egg_offsets[-1]) + egg_larva_days
    if len(tmean_from_first_egg) < required:
        raise InsufficientWeather(
            f"need {required} days of temperature from the first egg, "
            f"got {len(tmean_from_first_egg)}"
        )

    # windows[k] is the development window for the k-th egg. Building it as one
    # 2-D index keeps this a single vectorised gather.
    windows = tmean_from_first_egg[
        egg_offsets[:, None] + np.arange(egg_larva_days)[None, :]
    ]
    cold = windows < lower_dev_threshold
    hot = windows > upper_dev_threshold

    per_egg_days_outside = (cold | hot).sum(axis=1)
    per_egg_risk = np.clip(per_egg_days_outside * mortality_factor, 0.0, 1.0)

    return EggLarvaMortalityResult(
        mortality=float(per_egg_risk.mean()),
        mean_cold_days=float(cold.sum(axis=1).mean()),
        mean_hot_days=float(hot.sum(axis=1).mean()),
        n_eggs=int(egg_offsets.size),
    )


# ---------------------------------------------------------------------------
# Winter mortality -- Equations 4.7 and 4.8
# ---------------------------------------------------------------------------


@dataclass
class WinterMortalityResult:
    mortality: float  # [W] clipped to [0, 1]
    warm_days: int  # days above T_D during the pre-winter period


def winter_mortality(
    tmean_prewinter: np.ndarray,
    diapause_temp_threshold: float,
    winter_mortality_factor: float,
) -> WinterMortalityResult:
    """Winter mortality risk accrued during the pre-winter period.

    Equation 4.7 counts days between adult eclosion [SP, 15 Aug] and winter
    arrival [EP, 1 Oct] whose mean temperature is at or above the diapause
    threshold T_D, each adding W_F to the risk. Warm pre-winter conditions
    deplete the fat reserves needed to survive diapause (Sgolastra et al. 2011).

    Args:
        tmean_prewinter: Daily mean temperature (degC) over [SP, EP).
        diapause_temp_threshold: [T_D] degC, 15.
        winter_mortality_factor: [W_F] risk per warm day, 0.0025.
    """
    warm_days = int((tmean_prewinter >= diapause_temp_threshold).sum())
    return WinterMortalityResult(
        mortality=float(min(warm_days * winter_mortality_factor, 1.0)),
        warm_days=warm_days,
    )


# ---------------------------------------------------------------------------
# Reproductive success -- Equation 4.10
# ---------------------------------------------------------------------------


def reproductive_success(eggs: float, egg_larva_risk: float, winter_risk: float) -> float:
    """Adult offspring per female: ``R = E * (1 - M) * (1 - W)`` (Eq. 4.10)."""
    return float(eggs * (1.0 - egg_larva_risk) * (1.0 - winter_risk))
