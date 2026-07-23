# AppleBee replication notes

Replication of Chapter 4 of *Bridging AI and Ecology* (Amoah, Boyle, Smithwick &
Grozinger) — "AppleBee: an individual-based spatially explicit mechanistic model
to predict the reproductive success of wild solitary pollinators".

Everything here was produced by the code in `applebee/` and `scripts/`, from the
data already present in `archives/`. No data needed to be downloaded.

---

## 1. Results vs. the chapter

### Objective 3 — full AppleBee model vs. Osmia monitoring (Turley et al. 2022)

| Metric | Chapter | This replication |
|---|---|---|
| Default params, R² | 0.79 | **0.803** |
| Default params, RMSE | 7.69 | **7.52** |
| Calibrated params, R² | 0.77 | **0.797** |
| Calibrated params, RMSE | 8.13 | **7.63** |

The chapter's finding that the *default* (literature) parameters slightly
out-perform the *calibrated* ones also replicates.

### Objective 4 — statewide simulation, 7,452 cells × 16 years = 119,232 cell-years

| Metric | Chapter | This replication |
|---|---|---|
| Offspring per female, max | 30 | 34.4 |
| Offspring per female, mean | 17 | 15.4 |
| Offspring per female, min | 1 | 0.0 |
| Per-grid year-to-year SD, max | 9 | 9.6 |
| Per-grid year-to-year SD, mean | 5 | 5.3 |
| Per-grid year-to-year SD, min | 2 | 1.6 |
| No-egg days, temperature | 6.38 ± 3.82 | **6.63 ± 3.90** |
| No-egg days, precipitation | 4.40 ± 1.97 | **4.44 ± 1.99** |
| t (temperature > precipitation) | 158.23, p≈0 | 172.5, p≈0 |

Random-forest importance of the four sub-models (Figure 4-13) — same ranking,
same order of magnitude, and emergence date matches to three decimals:

| Sub-model | Chapter | This replication |
|---|---|---|
| Egg production | 98.348% | 96.598% |
| Egg and larva mortality | 1.596% | 3.291% |
| Winter mortality | 0.054% | 0.108% |
| Julian emergence date | 0.002% | **0.002%** |

Qualitative findings reproduce as well:

- **Spatial** — high reproductive success in the forested, higher-elevation
  north and north-east; low across the agricultural and developed south-east
  (Figure 4-12).
- **Temporal** — 2019, 2021 and 2023 are high years; **2018 is the clear
  minimum** (7.7 offspring per female vs. a 15.4 mean), with 2020 and 2022 also
  low. 2009 and 2018 have the highest temperature-limited no-egg days, matching
  the chapter's note that these coincide with low offspring production.

### Objective 2 — egg-production sub-model vs. Centrella et al. (2020)

This is the one objective that does **not** reproduce its absolute numbers.

| Metric | Chapter | This replication |
|---|---|---|
| Default params, R² | 0.52 | 0.36 – 0.41 |
| Calibrated params, R² | 0.60 | 0.44 – 0.48 |
| Improvement from calibration | +0.08 | **+0.07** |

The *direction and size of the calibration effect* replicate; the absolute level
does not. The cause is a data gap, not a model discrepancy — see §3.

**Sobol sensitivity (Figures 4-5, 4-6).** The best achievable R² replicates
closely — **0.593 here vs. 0.60 in the chapter** — but the ranking of parameters
differs:

| Parameter | Chapter S1 / ST | This replication S1 / ST |
|---|---|---|
| Temperature threshold | 0.18 / 0.33 | **0.680 / 0.759** |
| Precipitation threshold | 0.38 / 0.46 | 0.125 / 0.193 |
| Forage threshold | 0.30 / 0.37 | 0.103 / 0.149 |

(2,560 Saltelli samples; S1 confidence ±0.09 or better, so the ordering is
well separated.)

Worth flagging: **the chapter is internally inconsistent here.** Its body text
says "the precipitation threshold shows the highest sensitivity", but the
caption of Figure 4-5 states "the sensitivity analysis indicates that
temperature is the most sensitive model parameter". This replication agrees with
the caption. Because the sensitivity target is R² against the observed egg
counts, this ranking is also downstream of the §3 data gap — resolving that
should be done before treating either ranking as settled.

---

## 2. Defects found in the archived code

The rewrite in `applebee/` corrects the following. Each was verified against the
equations in the chapter.

1. **`winter_mortality.py` did not implement the winter mortality sub-model.**
   It computed mean temperature from 1 November to the following spring's
   emergence and returned a flat 50% mortality if that mean exceeded 6.53 °C —
   a rule that appears nowhere in the chapter. Equations 4.7–4.8 define winter
   mortality as pre-winter warm-day accumulation (15 Aug – 1 Oct, days ≥ 15 °C,
   × 0.25%), which is what the archived `pre_winter_mortality.py` actually
   implemented. The rewrite implements Eq. 4.7 as the winter mortality
   sub-model and drops the undocumented rule.

2. **`simulate.py` passed the wrong number of arguments.**
   `Simulator.winterMortality` called
   `getWinteringTemperature_vector(self, col, row, year, winter_delta, dev_temp)`
   — five arguments into a four-parameter function. Any call would raise
   `TypeError`.

3. **Emergence date was off by one day.** The vectorised path used
   `argwhere(cumsum > threshold)[0][0]` and then added one day, so emergence
   landed a day after the day CDD first met the constant. The chapter defines ED
   as the day CDD *equals or exceeds* DD. The two archived implementations
   (looping vs. vectorised) also disagreed with each other. Fixed to `>=` with
   direct indexing, and pinned by tests.

4. **Precipitation threshold used the wrong comparison.** Equation 4.3 makes a
   day favourable when `P_i ≤ P_H`; the code used `P_i < P_H`. Same for the
   forage threshold (`L_i ≥ L_H` vs. `>`). Fixed and pinned by boundary tests.

5. **Forage lookup queried a column that does not exist.**
   `getGridForageQuality` looked for `spring_resource_quality_{year}`, absent
   from every forage file in the repository. Every lookup therefore fell into a
   bare `except:` that walked ten neighbouring cells and years before silently
   returning a hard-coded **0.5** — exactly the threshold value, so missing
   forage data would flip cells to "abundant" with no trace. The rewrite reads
   the real 0–1 index from `data/forage.csv`, falls back only to the nearest
   available year *for the same cell*, and records every substitution
   (1,452 cell-years, all from the 2017 CDL gap).

6. **Hard-coded absolute paths.** `utils.py` loaded CSVs from
   `/Users/edwardamoah/Documents/GitHub/OsmiaPopModel/...` at import time, so
   the module could not be imported on any other machine. Paths now live in
   `applebee/config.py`.

7. **A silent data defect in the PRISM export.** `tmean_prism_pennsylvania_data_1990_2023.csv`
   contains 2024-04-23 twice, once as an `early` release and once as
   `provisional`. The loader now resolves duplicates by PRISM quality tier
   (stable > provisional > early) instead of taking whichever column came first.

8. **Per-egg mortality risk was not capped before averaging.** Equation 4.4
   averages per-egg *risks*; 18 days outside the thermal window gives 1.8 before
   capping. The archived code capped only the mean, letting one doomed egg
   inflate the average above what a probability allows. The rewrite caps per-egg
   risk at 1 before averaging.

Performance: the archived code ran a pandas `.query()` per cell per day. The
rewrite loads PRISM once into cached float32 matrices and indexes them directly,
which takes the full statewide simulation from impractical to **~20 seconds**
for all 119,232 cell-years.

---

## 3. Known gap: the Centrella observed-egg counts

The chapter reports observed six-day egg totals with max/mean/min/SD of
**206 / 65 / 12 / 42**. The Centrella extract in this repository
(`archives/research/data/Centrella_et_al_Data.csv`, 51 rows) records only
*emerged adults* and a larval-mortality proportion:

| Candidate definition | max | mean | min | SD |
|---|---|---|---|---|
| Chapter target | 206 | 65 | 12 | 42 |
| Emerged adults (M+F) | 175 | 46 | 4 | 38 |
| Adults ÷ (1 − larval mortality) | 182 | 52 | 4 | 41 |
| Females only | 93 | 22 | 0 | 20 |

No combination of the available columns reproduces the chapter's figures. The
chapter describes counting "the total number of eggs ... from the extracted
completed nest tubes", i.e. brood-cell counts including cells that never
produced an adult. Those raw counts are not in this repository's extract.

`load_centrella(observed_eggs=...)` therefore exposes the choice explicitly
(`emerged_adults` or `eggs_backcorrected`) rather than silently picking one, and
the reported R² is lower than the chapter's for that reason. **Obtaining the full
Centrella et al. (2020) brood-cell dataset is the one outstanding item needed to
close this objective.**

A second, smaller difference: the chapter describes collections "every 6 days",
but the recorded `Calendar_Date` values are irregular (time point 1 spans
20–27 May across sites). This replication uses each site's own recorded
collection date, which raised R² from 0.29 to 0.36–0.41 versus assuming a
regular cadence.

---

## 4. Modelling decisions the chapter leaves open

Recorded here because they affect results and a re-runner should know they were
choices, not deductions:

- **No-egg-day attribution.** A day can be blocked by low temperature *and* high
  rain at once. Temperature- and precipitation-limited days are counted
  independently, so the two counts can sum to more than the number of blocked
  days. This matches the chapter's reported means closely (6.63 vs 6.38, 4.44 vs
  4.40), supporting the interpretation.
- **Offspring year offset.** Offspring produced in weather year *Y* are counted
  as the abundance of spring *Y+1*, so weather years 2008–2023 report
  reproductive success for 2009–2024, per Eq. 4.10 and the chapter's framing.
- **2017 forage gap.** The CDL forage summary is missing 1,452 Pennsylvania
  cells for 2017; these fall back to the nearest year for the same cell.
