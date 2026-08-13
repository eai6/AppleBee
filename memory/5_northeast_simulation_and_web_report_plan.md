# 5 — Northeast simulation and web report

**Date:** 2026-08-07
**Purpose:** Run AppleBee across the Northeast now that plan 4 supplied the
inputs, wire it into the evaluation notebook, and publish the results as a web
page.

## Context

Plan 4 delivered both missing datasets for 2013–2018:

- PRISM daily `tmean` and `ppt`, 102,555 cells × 2,191 days, verified
  **100.0000% identical** to the archived Pennsylvania export where they overlap
- Lonsdorf spring forage from the national CDL, **44,759 cells in every one of
  the six years** — an exactly balanced panel

44,759 cells carry both, so the simulation extent is no longer Pennsylvania.

## The run

`scripts/run_northeast_simulation.py` — weather years 2013–2018 → offspring
springs 2014–2019. **268,536 cell-years in 38 s**, 18 failures
(`InsufficientWeather`: 3 far-northern cells × 6 years never accumulate the
209 degree-days needed to emerge — a real ecological boundary, not a defect).

| Metric | Northeast | Pennsylvania only |
|---|---|---|
| Cell-years | 268,536 | 119,232 |
| Offspring/female, mean | **14.73** | 15.44 |
| max / min | 34.8 / 0.00 | 34.4 / 0.00 |
| Within-cell SD through time | 4.99 | 5.27 |
| Between-cell SD of means | 4.59 | 4.67 |

Per year (offspring spring): 2014 13.07, **2015 18.03**, 2016 14.55, 2017 12.97,
**2018 12.38**, 2019 17.41. Best year is 1.46× the worst.

### What the wider extent shows that Pennsylvania could not

- **A north–south gradient**, and it runs the opposite way to intuition: the
  northern half averages **16.07** against the southern half's **13.40**. Cooler
  northern cells do better, consistent with the chapter's Pennsylvania finding
  that the forested, higher-elevation north scores highest.
- **Emergence spans 56–187 day-of-year** across the region (mean 131), against a
  much narrower range within Pennsylvania.
- Per-cell means run **4.3 to 26.8**, a sixfold spread.

### Drivers, correlated against the annual regional mean

| Driver | r |
|---|---|
| Eggs laid | **+0.996** |
| Temperature-limited no-egg days | **−0.981** |
| Egg/larva mortality | −0.953 |
| Emergence day | +0.702 |
| Precipitation-limited no-egg days | −0.470 |
| Winter mortality | +0.241 |

Egg production dominates, and temperature is what gates it — 6.66 ± 3.63
temperature-limited days against 4.47 ± 2.06 precipitation-limited. This
reproduces the Pennsylvania result on four times the area.

## Plan

- [x] `scripts/run_northeast_simulation.py`
- [x] Run and summarise
- [x] Point the notebook's Part 3 at the Northeast, keeping Pennsylvania as a
      fallback when the acquired inputs are absent
- [x] Publish a web report of the run

## Progress / outcome

**Notebook** — `notebooks/applebee_evaluation_and_simulation.ipynb` Part 3 now
detects the acquired Northeast inputs and uses them, falling back to
Pennsylvania when they are absent so the notebook still runs on a fresh clone.
Executed end to end: 21 code cells, 0 errors, 8 figures, ~22 s.

Labels that had been hardcoded for the Pennsylvania run ("SD of a cell's 16
annual values", "SD of the 7,452 cell means") are now derived from the data —
they read 6 and 44,756 on this run. Worth noting because they would have been
quietly wrong rather than visibly broken.

The monitoring site from Part 2 sits at the **6th percentile** of Northeast cells
by six-year mean (7.51 against a regional 14.73), which sharpens the point that
one site cannot characterise the model.

**Web report** — published at
<https://claude.ai/code/artifact/90dd0a2f-9da5-476c-a6c9-5a7931af436c>.
Interactive canvas map of all 44,756 cells with a year selector and hover
readout, the six-year series, the driver correlations, the north–south finding,
and provenance. Per-cell values are packed as base64 `Uint16` arrays (coordinates
once, one value array per year) giving a 933 KB payload for 268,536 values.

The page states plainly what the run does *not* establish: a larger simulation is
not a better-validated model, and the field evaluation still rests on six annual
observations explaining 21% of variance at p = 0.36.

## Decisions taken

- **Weather years 2013–2018 → springs 2014–2019.** Set by the forage series;
  extending needs more CDL years, which is now cheap (one national raster each).
- **Cells needing both weather and forage** — 44,756 of 44,759 run; the three
  that fail are genuine cold-limit cells and are reported, not hidden.

## Commits

| SHA | Date | Subject |
|---|---|---|
| `8129722` | 2026-08-08 | Simulate the Northeast and the contiguous United States, 2014-2019 |
| `3ea2cf1` | 2026-08-13 | Repair a half-written day in the CONUS weather cache |

## Follow-ups

- The evaluation gap from plans 2–3 is untouched by this. A bigger simulation is
  not a better-validated model: Objective 3 still rests on six points, and
  Objective 2 still lacks its response variable.
- Extending to 2008–2024 is now ~11 more national CDL years plus the PRISM days,
  and would let the Northeast run match the chapter's 16-year Pennsylvania one.
