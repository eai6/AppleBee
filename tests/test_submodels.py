"""Sub-model tests pinned to the worked examples in the AppleBee chapter."""

import numpy as np
import pytest

from applebee.submodels import (
    InsufficientWeather,
    egg_larva_mortality,
    egg_production,
    emergence_date,
    reproductive_success,
    winter_mortality,
)

# ---------------------------------------------------------------------------
# Emergence date (Eq. 4.1)
# ---------------------------------------------------------------------------


def test_emergence_accumulates_only_above_base_temp():
    # 10 degC against a 6.53 base contributes 3.47 degree-days per day.
    # 209 / 3.47 = 60.2, so the threshold is first met on day 61.
    tmean = np.full(200, 10.0)
    result = emergence_date(tmean, base_temp=6.53, thermal_constant=209.0)
    assert result.day_of_year == 61
    assert result.cumulative_degree_days >= 209.0


def test_emergence_ignores_days_below_base_temp():
    # Thirty freezing days must not push emergence earlier, and must not
    # subtract from the accumulator either.
    warm = np.full(200, 10.0)
    with_cold = np.concatenate([np.full(30, -5.0), warm])
    assert emergence_date(with_cold, 6.53, 209.0).day_of_year == 61 + 30


def test_emergence_day_one_is_january_first():
    # A single enormous day must emerge on day-of-year 1, not 0 or 2.
    tmean = np.concatenate([[1000.0], np.full(10, 10.0)])
    assert emergence_date(tmean, 6.53, 209.0).day_of_year == 1


def test_emergence_boundary_is_inclusive():
    # ED is the day CDD "equals or exceeds" DD, so exact equality counts.
    tmean = np.full(10, 6.53 + 20.9)  # exactly 20.9 degree-days per day
    assert emergence_date(tmean, 6.53, 209.0).day_of_year == 10


def test_emergence_raises_when_threshold_never_reached():
    with pytest.raises(InsufficientWeather):
        emergence_date(np.full(365, 5.0), 6.53, 209.0)


# ---------------------------------------------------------------------------
# Egg production (Eqs. 4.2-4.3)
# ---------------------------------------------------------------------------


def test_egg_production_two_eggs_per_day_when_forage_abundant():
    tmean = np.full(20, 20.0)  # all above T_H
    ppt = np.zeros(20)  # all below P_H
    r = egg_production(tmean, ppt, 0.8, 13.9, 5.0, 0.5)
    assert r.eggs_per_day == 2
    assert r.eggs == 40
    assert r.no_egg_days == 0


def test_egg_production_one_egg_per_day_when_forage_scarce():
    r = egg_production(np.full(20, 20.0), np.zeros(20), 0.3, 13.9, 5.0, 0.5)
    assert r.eggs_per_day == 1
    assert r.eggs == 20


def test_egg_production_forage_threshold_is_inclusive():
    # Eq. 4.3 gives 2 eggs when L_i >= L_H, so a cell exactly at the threshold
    # counts as abundant.
    r = egg_production(np.full(20, 20.0), np.zeros(20), 0.5, 13.9, 5.0, 0.5)
    assert r.eggs_per_day == 2


def test_egg_production_blocks_cold_and_wet_days():
    tmean = np.array([20.0] * 10 + [5.0] * 10)  # last 10 too cold
    ppt = np.array([0.0] * 15 + [50.0] * 5)  # last 5 too wet
    r = egg_production(tmean, ppt, 0.8, 13.9, 5.0, 0.5)
    assert r.eggs == 20  # only the first 10 days are favourable
    assert r.no_egg_days_temperature == 10
    assert r.no_egg_days_precipitation == 5


def test_egg_production_thresholds_are_inclusive_per_equation_43():
    # Favourable when T >= T_H and P <= P_H; both boundaries count.
    r = egg_production(np.full(5, 13.9), np.full(5, 5.0), 0.8, 13.9, 5.0, 0.5)
    assert r.eggs == 10


def test_egg_production_rejects_mismatched_windows():
    with pytest.raises(ValueError):
        egg_production(np.zeros(20), np.zeros(19), 0.8, 13.9, 5.0, 0.5)


# ---------------------------------------------------------------------------
# Egg and larva mortality (Eqs. 4.4-4.6)
# ---------------------------------------------------------------------------


def test_no_mortality_inside_thermal_window():
    tmean = np.full(40, 20.0)  # comfortably inside [10, 30]
    r = egg_larva_mortality(tmean, np.array([0, 1, 2]), 18, 0.10, 10.0, 30.0)
    assert r.mortality == 0.0


def test_one_extreme_day_gives_ten_percent_risk():
    # The chapter: "an egg that experiences a cold or warm temperature for
    # 1 day will have a mortality risk of 10%".
    tmean = np.full(20, 20.0)
    tmean[0] = 35.0
    r = egg_larva_mortality(tmean, np.array([0]), 18, 0.10, 10.0, 30.0)
    assert r.mortality == pytest.approx(0.10)
    assert r.mean_hot_days == 1.0


def test_five_extreme_days_give_fifty_percent_risk():
    # "an egg that experiences 5 warm temperature days will have a mortality
    # risk of 50%".
    tmean = np.full(20, 20.0)
    tmean[:5] = 35.0
    r = egg_larva_mortality(tmean, np.array([0]), 18, 0.10, 10.0, 30.0)
    assert r.mortality == pytest.approx(0.50)


def test_per_egg_risk_is_capped_at_one():
    # 18 days all outside the window would give 1.8 without the cap.
    tmean = np.full(20, 40.0)
    r = egg_larva_mortality(tmean, np.array([0]), 18, 0.10, 10.0, 30.0)
    assert r.mortality == pytest.approx(1.0)


def test_mortality_averages_across_eggs():
    # Egg A sees no extremes, egg B sees five hot days: mean risk is 25%.
    tmean = np.full(40, 20.0)
    tmean[20:25] = 35.0
    r = egg_larva_mortality(tmean, np.array([0, 20]), 18, 0.10, 10.0, 30.0)
    assert r.mortality == pytest.approx(0.25)
    assert r.n_eggs == 2


def test_thermal_window_boundaries_are_safe():
    # Eq. 4.6 gives risk 0 when LDT <= T <= UDT, so both bounds are survivable.
    tmean = np.concatenate([np.full(9, 10.0), np.full(11, 30.0)])
    r = egg_larva_mortality(tmean, np.array([0]), 18, 0.10, 10.0, 30.0)
    assert r.mortality == 0.0


def test_no_eggs_means_no_mortality():
    r = egg_larva_mortality(np.empty(0), np.array([], dtype=int), 18, 0.10, 10.0, 30.0)
    assert r.mortality == 0.0 and r.n_eggs == 0


def test_short_temperature_record_is_an_error_not_a_silent_truncation():
    with pytest.raises(InsufficientWeather):
        egg_larva_mortality(np.full(10, 20.0), np.array([0]), 18, 0.10, 10.0, 30.0)


# ---------------------------------------------------------------------------
# Winter mortality (Eqs. 4.7-4.8)
# ---------------------------------------------------------------------------


def test_sixty_warm_prewinter_days_give_fifteen_percent_mortality():
    # The chapter calibrates W_F so that "a late winter arrival or 60 days of
    # pre-wintering will result in a winter mortality of 15%".
    r = winter_mortality(np.full(60, 20.0), 15.0, 0.0025)
    assert r.mortality == pytest.approx(0.15)
    assert r.warm_days == 60


def test_cold_prewinter_gives_no_winter_mortality():
    r = winter_mortality(np.full(47, 5.0), 15.0, 0.0025)
    assert r.mortality == 0.0


def test_only_days_above_the_diapause_threshold_count():
    tmean = np.array([20.0] * 10 + [5.0] * 37)
    assert winter_mortality(tmean, 15.0, 0.0025).warm_days == 10


def test_winter_mortality_is_capped_at_one():
    r = winter_mortality(np.full(1000, 20.0), 15.0, 0.0025)
    assert r.mortality == 1.0


# ---------------------------------------------------------------------------
# Reproductive success (Eq. 4.10)
# ---------------------------------------------------------------------------


def test_reproductive_success_compounds_both_mortalities():
    # R = E * (1 - M) * (1 - W)
    assert reproductive_success(40, 0.25, 0.15) == pytest.approx(40 * 0.75 * 0.85)


def test_total_mortality_leaves_no_offspring():
    assert reproductive_success(40, 1.0, 0.0) == 0.0
    assert reproductive_success(40, 0.0, 1.0) == 0.0
