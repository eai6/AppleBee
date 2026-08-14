# AppleBee replication notes

Replication of Chapter 4 of *Bridging AI and Ecology* (Amoah, Boyle, Smithwick &
Grozinger) — "AppleBee: an individual-based spatially explicit mechanistic model
to predict the reproductive success of wild solitary pollinators".

Everything here was produced by the code in `applebee/` and `scripts/`, from the
data catalogued in [`data/inputs/MANIFEST.md`](../data/inputs/MANIFEST.md).
Nothing needed to be downloaded.

---

## 0. Verdict

| Objective | Chapter | Replication | Status |
|---|---|---|---|
| 2 — egg production vs Centrella | R² 0.52 | **0.510** | **replicates** (§3) |
| 2 — best achievable R² | 0.60 | **0.601–0.643** | **replicates**; the optimum sits at different thresholds (§3, §4) |
| 2 — observed egg distribution | 206 / 65 / 12 / 42 | 182 / 52 / 4 / 41 | **unresolved** — not derivable from the published dataset (§3) |
| 2 — Sobol ranking | precipitation most sensitive | temperature most sensitive | **fails** — precipitation cannot be most sensitive over the Table 4-5 ranges, and the chapter contradicts itself (§4) |
| 3 — full model vs Turley | R² 0.79, RMSE 7.69 | **0.803, RMSE 7.52** | **replicates** |
| 3 — calibrated params | R² 0.77, RMSE 8.13 | 0.797, RMSE 7.63 | **replicates** |
| 3 — slope and significance | β 1.82 / 1.51, p > 0.05 | β 1.99 / 2.31, p ≈ 0.001 | **fails** — `statsmodels` gives a standard error 3.1× too small under a singleton random effect; the chapter's non-significant finding is the defensible one (§2) |
| 4 — statewide simulation | mean 17, min 1 | 15.4, 0.0 | **reconciled** by one reading of the foraging period (§5) |
| 4 — no-egg days, RF importance | 6.38 / 4.40; egg production dominant | 6.63 / 4.44; same ranking | **replicates** |
| 4 — spatial and temporal pattern | forested north high, 2018 the minimum | same | **replicates** |

Two findings below are about the chapter rather than the code: its winter
mortality worked example is impossible inside its own window (§6), and its Sobol
body text disagrees with its own figure caption (§4).

---

## 1. What replicates cleanly

### Objective 4 — statewide, 7,452 cells × 16 weather years = 119,232 cell-years

| Metric | Chapter | This replication |
|---|---|---|
| No-egg days, temperature | 6.38 ± 3.82 | **6.63 ± 3.90** |
| No-egg days, precipitation | 4.40 ± 1.97 | **4.44 ± 1.99** |
| t (temperature > precipitation) | 158.23, p≈0 | 172.5, p≈0 |
| Per-cell year-to-year SD, max/mean/min | 9 / 5 / 2 | 9.6 / 5.3 / 1.6 |

Random-forest importance of the four sub-models (Figure 4-13) — same ranking,
same order of magnitude:

| Sub-model | Chapter | This replication |
|---|---|---|
| Egg production | 98.348% | 96.598% |
| Egg and larva mortality | 1.596% | 3.291% |
| Winter mortality | 0.054% | 0.108% |
| Julian emergence date | 0.002% | **0.002%** |

Qualitative findings reproduce:

- **Spatial** — high reproductive success in the forested, higher-elevation
  north and north-east; low across the agricultural and developed south-east
  (Figure 4-12).
- **Temporal** — 2019, 2021 and 2023 are high years; **2018 is the clear
  minimum** (7.7 offspring per female against a 15.4 mean), with 2020 and 2022
  also low. 2009 and 2018 have the most temperature-limited no-egg days, matching
  the chapter's note that these coincide with low offspring production.

---

## 2. Objective 3 replicates; the R² definition is an open question

**The headline result reproduces.** Equation 4.11 as the chapter specifies it —
`observed ~ predicted` with a random intercept by year, on six annual *Osmia*
counts — gives:

| | Chapter | This replication |
|---|---|---|
| Default params, R² | 0.79 | **0.803** |
| Default params, RMSE | 7.69 | **7.52** |
| Calibrated, R² | 0.77 | **0.797** |
| Calibrated, RMSE | 8.13 | **7.63** |

An independent implementation lands within 0.013 of the published figure, and
reproduces the chapter's finding that default parameters slightly out-perform
calibrated ones. Nothing about the arithmetic or the reproduction is in doubt.

The rest of this section records a **question about what the statistic measures**,
raised during the replication and left open pending statistical advice
(user decision, 2026-08-08). It is recorded here because it is what a statistician
would need to see, not as a verdict on the chapter.

Equation 4.11 is fitted with a random intercept by year on six observations
covering six years — one observation per group. Whether the variance components
are separable under that design is the open question. Decomposing the fit:

| | R² |
|---|---|
| Conditional (fixed + random, what gets reported) | **0.803** |
| Marginal (fixed effects only — what AppleBee explains) | **0.212** |
| Plain OLS on the same six points | 0.212, **p = 0.36** |

Under a plain OLS on the same six points the slope is not significant
(Pearson r = 0.46, 95% CI roughly −0.56 to 0.93), and `statsmodels` reports
`ConvergenceWarning: The Hessian matrix at the estimated parameter values is not
positive definite` for the mixed fit.

### The conditional R² is arithmetically forced, not estimated

With one observation per group the variance components are not separable, and
`statsmodels` settles on **group variance = residual scale = 169.5554** — equal to
four decimal places. Equal components give a shrinkage factor of exactly ½, so
every fitted value is the midpoint of the marginal prediction and that year's own
observation. Verified across all six years:

```
shrinkage toward each year's own observation: [0.5]
```

Halving every residual quarters the error sum of squares, so the conditional R²
follows from the marginal one by arithmetic:

    1 − (1 − 0.2121) / 4 = 0.8030   =   the reported conditional R²

to four decimal places. The 0.79/0.803 is therefore not an independent measure of
fit — it is 0.212 passed through a shrinkage constant that the design fixed in
advance. Any marginal R² would have mapped to a conditional one the same way.

### The coefficient does *not* replicate

R² and RMSE reproduce, but the slope and its p-value do not:

| | Chapter | This replication |
|---|---|---|
| Default, β | 1.82, **p > 0.05** | **1.99, p = 0.001** |
| Calibrated, β | 1.51, **p > 0.05** | **2.31, p = 0.002** |

Same six points, same equation, opposite conclusion on significance — so one of
the two fits is misbehaving, and the evidence points at this one. `statsmodels`
returns a standard error of **0.618** against OLS's **1.922** on the same data,
3.1× smaller, and tests it with a *z* statistic assuming asymptotic normality at
n = 6. That is the same non-identifiability as above, surfacing in the standard
error instead of the R².

**The chapter's conclusion is the defensible one.** It reports the effect as
positive but not statistically significant, "likely due to the small sample size
(n = 6)" — which is both correct and more conservative than what this
implementation prints. The p ≈ 0.001 here should not be read as evidence.

**The chapter's 0.79 is reproducible and is what its stated method produces.**
Which of these two R² definitions should be reported is a question for a
statistician; §2b records the same comparison on a panel with replication, which
is the evidence most useful to that conversation.

The same decomposition on Objective 2, where the random effect *is* identifiable
(51 observations, 17 sites × 3 time points): marginal R² 0.175, conditional
0.410. Less extreme, but the reported figure is still mostly the site intercept.

A panel with genuine replication would settle it — many observations per group,
so the variance components are separable. See §2b.

---

## 2b. Withdrawn — the Biddinger evaluation

An evaluation of Objective 3 against a larger *Osmia* specimen database was built
and then withdrawn from this repository (2026-08-13, at the author's direction).
The data, module, tests and outputs are removed; the work remains in git history
at `e5b2367` and in `memory/3_biddinger_objective3_evaluation_plan.md`.

The one result worth carrying forward: reconstructing Turley's own eight-farm
sampling frame reproduced his published annual counts at r = 0.963, and running
that same frame over 13 years rather than 6 showed no detectable relationship
with predicted offspring. That bears on the open question in §2 about what
Equation 4.11's R² measures, and is recorded here so the question is not lost
with the data.

---

## 3. Objective 2 replicates — after correcting a window off-by-one

**This section previously reported that Objective 2 failed. That was my error,
not the chapter's.** The cause was a one-day offset in how I built the collection
windows, found on 2026-08-13 by taking seriously the fact that the chapter also
reports its *predicted* egg statistics.

### The bug

Nest tubes were retrieved and replaced roughly every six days. I built each
window as the six days *ending the day before* collection — `[D-6, D-1]` —
excluding the collection day itself. A tube retrieved on day D holds the eggs
laid up to and including D, so the window should be `[D-5, D]`.

In this dataset that one day matters enormously, because 25–30 May 2015 is a run
of **six consecutive fully favourable days at all 17 sites** (warm, no rain).
Shifting every window a day early missed that run entirely.

The chapter's own reported predicted-egg statistics are what exposed it:

| Predicted eggs per window | max | mean | min | SD |
|---|---|---|---|---|
| Chapter | **12** | 3 | 0 | 2 |
| Mine, window `[D-6, D-1]` | **10** | 3.45 | 1 | 1.74 |
| Mine, window `[D-5, D]` | **12** | 3.61 | 1 | 1.96 |

A maximum of 12 requires six favourable days at 2 eggs/day. Ten was arithmetically
impossible to reconcile with the chapter, and that should have been the first
thing I checked.

### With the window corrected

| Metric | Chapter | This replication |
|---|---|---|
| Default params, R² | 0.52 | **0.510** |
| Best achievable R² | 0.60 | **0.601** (grid) / **0.643** (Saltelli, 2,560 samples) |

**Objective 2's headline numbers replicate.** The default-parameter fit lands
within 0.01, and the best achievable R² reproduces the chapter's 0.60 to three
decimals.

Two differences remain, both smaller than the one I had wrong:

- **The calibration *gain* no longer replicates.** Before the window fix the gain
  was +0.068 against the chapter's +0.08, which looked like a clean reproduction.
  With the window corrected the default fit rises to 0.510 while the chapter's
  calibrated thresholds give 0.521, so the gain is **+0.011**. Fixing a real bug
  improved one comparison and worsened another; both are reported.
- **The calibration optimum sits elsewhere.** The chapter reports its best fit at
  forage 0.54, temperature 18.72 °C, precipitation 4.33 mm; the same search here
  peaks at 0.50 / 21.0 / 6.0. At the chapter's own values this implementation
  gives R² 0.521 rather than 0.60, so the ridge is flat and the located optimum
  is not well identified.
- **The observed egg distribution still does not match**, and that remains
  unexplained — see below.

### Still unresolved: the observed counts

The chapter reports observed six-day egg totals of max/mean/min/SD
**206 / 65 / 12 / 42**. The published dataset records emerged adults and a
larval-mortality proportion. Reconstructing cells as
`(males + females) / (1 - larval mortality)` — the chapter's own approach — gives
**182 / 52 / 4 / 41**.

That reconstruction is bounded below by the adult count, because larval mortality
cannot be negative, and **11 of 51 rows record mortality of exactly 0.000** so
receive no correction at all. The smallest row has 4 adults and zero recorded
mortality; reaching the chapter's minimum of 12 from it would need a mortality of
0.67. No combination of the available columns reproduces the target distribution.

Note this no longer prevents the R² from replicating: with the corrected window,
the fit reaches 0.510 using the back-corrected counts and 0.460 using raw emerged
adults. Whether the published summary statistics came from a fuller dataset, or
are themselves in error, is a question for the authors — but it is no longer
load-bearing for the replication.

A second, smaller difference: the chapter describes collections "every 6 days",
but the recorded `Calendar_Date` values are irregular (time point 1 spans 20–27
May across sites). This replication uses each site's own recorded collection date.

## 4. The Sobol ranking flip is real, and independent of everything else

| Parameter | Chapter S1 / ST | This replication S1 / ST |
|---|---|---|
| Temperature threshold | 0.18 / 0.33 | **0.621 / 0.694** |
| Precipitation threshold | 0.38 / 0.46 | 0.131 / 0.220 |
| Forage threshold | 0.30 / 0.37 | 0.118 / 0.156 |

Re-run after the §3 window correction. That fix raised the best achievable R²
from 0.586 to **0.643** but left the ranking untouched, so it is not the cause
of the disagreement.

2,560 Saltelli samples; S1 confidence ±0.10 or better, so the ordering is well
separated. Best achievable R² replicates — **0.643 here against 0.60 in the
chapter** — but at different thresholds (temperature 21.4 °C, precipitation
8.3 mm here; 18.72 °C and 4.33 mm in the chapter).

Because the sensitivity target is R² against the observed egg counts, the
obvious worry is that this ranking is downstream of §3. **It is not.** Re-running
the analysis under both definitions of the observed response (N = 256, 1,280
model evaluations each) leaves the ranking unchanged:

| Response | forage S1/ST | temperature S1/ST | precipitation S1/ST |
|---|---|---|---|
| emerged adults | 0.137 / 0.185 | **0.594 / 0.700** | 0.138 / 0.215 |
| back-corrected eggs | 0.138 / 0.160 | **0.659 / 0.766** | 0.092 / 0.223 |

Temperature dominates by a factor of four either way. The flip is a genuine
disagreement with the chapter, not an artefact of the missing data.

### Why precipitation cannot be the most sensitive parameter here

Two further candidate explanations were tested and rejected, and the third is
mechanical.

**Rejected — the comparison operator.** The archived code used `P_i < P_H` where
Eq. 4.3 says `P_i ≤ P_H` (defect 7.4), and 51.2% of days in the Centrella window
have *exactly* 0.0 mm of rain, so the two operators disagree on half the record
at `P_H = 0`. That looks like it should matter enormously. It does not: the
operators differ **only on exact ties**, and Saltelli draws `P_H` from a
continuum, so a tie arises essentially only at `P_H = 0.0` exactly. Re-running
the full analysis under the archived operator gives Sobol indices identical to
four decimals.

**Rejected — the sensitivity target.** Running Sobol against mean *predicted
eggs* (sensitivity of the model itself) rather than R² against observations
moves the indices but not the ranking:

| Target | forage S1 | temperature S1 | precipitation S1 |
|---|---|---|---|
| R² against observed | 0.098 | **0.649** | 0.113 |
| mean predicted eggs | 0.203 | **0.753** | 0.019 |

**The actual reason: precipitation barely gates any days over the range in
Table 4-5.** Sweeping each threshold across its stated range, holding the others
at their defaults:

| Threshold | Range (Table 4-5) | Mean eggs across the range | Swing |
|---|---|---|---|
| Temperature `T_H` | 10–22 °C | 5.0 → 0.8 | **4.2** |
| Forage `L_H` | 0.4–0.6 | 4.9 → 2.8 | 2.0 |
| Precipitation `P_H` | 0–10 mm | 3.1 → 3.9 | **0.8** |

The underlying day counts explain it. Over its whole range the temperature gate
swings the share of admissible days by **78 points** (94.1% at 10 °C down to
15.7% at 22 °C), because May–June mean temperatures in the Finger Lakes sit
squarely across 10–22 °C. The precipitation gate swings only **34 points**
(51.2% at 0 mm to 85.6% at 10 mm) — and it cannot do better, because 51% of days
are already bone dry and pass at *any* threshold, while the wet days it excludes
are largely ones the temperature gate has excluded anyway. The forage threshold
flips 12 of the 17 sites across 0.4–0.6, which is why it lands in between.

So **precipitation is the least influential of the three over the stated ranges,
and no implementation choice makes it the most influential.** The chapter's
S1 = 0.38 for precipitation is not reachable from the model as specified.

Worth flagging: **the chapter is internally inconsistent here.** Its body text
says "the precipitation threshold shows the highest sensitivity", while the
caption of Figure 4-5 states "the sensitivity analysis indicates that temperature
is the most sensitive model parameter". This replication agrees with the caption,
and the mechanism above says the caption is the one that can be right.

---

## 5. Objective 4's mean and minimum are reconciled by one reading of the foraging period

| Metric | Chapter | As implemented | Foraging = full EF after mating |
|---|---|---|---|
| Offspring per female, mean | 17 | 15.44 | **17.05** |
| Offspring per female, min | 1 | 0.00 | **0.71** |
| Offspring per female, max | 30 | 34.4 | 36.3 |

The chapter gives longevity EF = 22 days and mating = 2 days but does not say
whether the two mating days come *out of* the 22 or *precede* them. The
implementation takes the first reading, giving a 20-day foraging window. Taking
the second — the female mates for 2 days and then forages for a full 22 —
moves the statewide mean from 15.44 to 17.05 and the minimum from 0.00 to 0.71,
matching both of the chapter's rounded figures at once.

That is strong enough to treat as the chapter's intent, but it is an inference,
not a deduction, so the code keeps the 20-day reading and this note records the
alternative. The maximum reconciles under neither reading (34.4 or 36.3 against
30); the chapter's 30 / 17 / 1 and 9 / 5 / 2 are all round integers, which
suggests they were read off figure legends rather than computed, so comparing
them to two decimals is over-precision either way.

---

## 6. The chapter's winter-mortality example is impossible inside its own window

Equations 4.7–4.8 accumulate winter mortality risk over the pre-winter period
[SP = 15 August, EP = 1 October) at W_F = 0.25% per day at or above T_D = 15 °C.
The chapter illustrates this with **sixty warm pre-winter days giving 15%
mortality**.

That window is **47 days long.** Sixty warm days cannot occur in it, and the
maximum attainable winter mortality is 47 × 0.0025 = **11.75%**. The statewide
simulation confirms the bound is reached: across all 119,232 cell-years,
`prewinter_warm_days` runs 19–47 and winter mortality runs 4.75%–11.75%.

Either the period or the worked example is wrong in the chapter. The code
implements the period as stated. The test suite pins the 60-day example against a
synthetic array, so it passes without exposing the contradiction — that test
verifies the equation, not the window.

---

## 7. Defects in the archived code — verified line by line

Each claim was re-checked against `archives/Python_scripts/simulator/`.

| # | Claim | Verdict |
|---|---|---|
| 1 | `winter_mortality.py` does not implement the winter sub-model | **confirmed** |
| 2 | `simulate.py` passes the wrong number of arguments | **confirmed** |
| 3 | Emergence date off by one day | **confirmed**; one sub-claim overstated |
| 4 | Precipitation threshold comparison wrong | **confirmed**; the forage half of the claim is **wrong** |
| 5 | Forage lookup falls through to a hard-coded 0.5 | **confirmed** |
| 6 | Hard-coded absolute paths | **confirmed**, and it conceals a worse bug |
| 7 | Duplicated day in the PRISM export | **confirmed** |
| 8 | Per-egg mortality risk not capped before averaging | **confirmed** |

**1. `winter_mortality.py` did not implement the winter mortality sub-model.**
`winter_mortality.py:34-45` (and `:116-127` in the vectorised path) computes mean
temperature from 1 November to the following spring's emergence and returns a
flat 50% mortality if that mean exceeds 6.53 °C — a rule that appears nowhere in
the chapter. 6.53 is the *emergence base temperature* from Table 4-1, reused here
as a winter threshold. Equations 4.7–4.8 define winter mortality as pre-winter
warm-day accumulation, which is what the archived `pre_winter_mortality.py`
actually implemented. The rewrite implements Eq. 4.7 and drops the undocumented
rule.

**2. `simulate.py` passes the wrong number of arguments.** `simulate.py:204`
calls `getWinteringTemperature_vector(self, col, row, year, winter_delta,
dev_temp)` — six arguments into the five-parameter signature at
`winter_mortality.py:103`. Any call raises `TypeError`, so this path was never
executed. (The earlier note said "five into four"; the miscount does not change
the finding.)

**3. Emergence date was off by one day.** `emergence.py:112-114` takes
`argwhere(cumsum > threshold)[0][0]` and then adds one day, landing a day after
the day CDD first met DD. The chapter defines ED as the day CDD *equals or
exceeds* DD. Fixed to `>=` with direct indexing, pinned by tests.

*Overstated sub-claim:* the earlier note said the looping and vectorised paths
disagreed with each other. They do not, except at exact equality — the loop at
`emergence.py:38` exits after incrementing past the crossing day, so both return
crossing-day + 1. Both are wrong in the same direction by the same amount.

**4. Precipitation threshold used the wrong comparison.** Equation 4.3 makes a
day favourable when `P_i ≤ P_H`; `egg_production.py:62` uses `daily_ppt <
precipitation_threshold`. Confirmed and fixed.

*Wrong sub-claim:* the earlier note also asserted the forage comparison was
wrong. It was not. `egg_production.py:39-42` assigns 2 eggs/day when
`forage_quality >= forage_threshold`, exactly as Eq. 4.3 specifies. The rewrite
did not change behaviour here, and the boundary test pins correct behaviour that
the archive already had.

**5. Forage lookup queried a column that does not exist.** `simulate.py:74`
looks for `spring_resource_quality_{year}`, absent from every forage file in the
repository. Every lookup falls into a bare `except:` that walks ten neighbouring
cells and years (`simulate.py:76-96`) before returning a hard-coded **0.5** at
`simulate.py:97` — exactly the default threshold value, so missing forage data
flips cells to "abundant" with no trace. The rewrite reads the real 0–1 index,
falls back only to the nearest available year *for the same cell*, and records
every substitution (1,452 cell-years, all from the 2017 CDL gap).

**6. Hard-coded absolute paths — and a data mix-up they hide.** `utils.py:5-8`
loads CSVs from `/Users/edwardamoah/Documents/GitHub/OsmiaPopModel/...` at import
time, so the module cannot be imported on another machine. Paths now live in
`applebee/config.py`.

*Not previously noted, and worse:* `utils.py:8` loads the **forage** table from
`tmean_prism_new_york_data.csv` — the temperature file — with the correct line
commented out directly above it. `getGridForageQuality` at `utils.py:39` then
queries a `sprng__` column on that frame, and on failure at `:41` recurses on
`year + 1` with no termination condition, so a miss recurses until
`RecursionError`. This module's forage lookup could never have returned a valid
value.

**7. A silent data defect in the PRISM export.** The Pennsylvania temperature
file carries 12,602 day columns for 12,601 distinct days: 2024-04-23 appears
twice, once as `early` and once as `provisional`. The loader now resolves
duplicates by PRISM quality tier (stable > provisional > early) rather than
taking whichever column came first (`applebee/weather.py:34`).

**8. Per-egg mortality risk was not capped before averaging.** Equation 4.4
averages per-egg *risks*; 18 days outside the thermal window gives 1.8 before
capping. `egg_and_larva_mortality.py:53-55` (loop) and `:134-136` (vectorised)
cap only the mean, letting one doomed egg inflate the average above what a
probability allows. The rewrite caps per-egg risk at 1 before averaging.

**Performance.** The archived code ran a pandas `.query()` per cell per day. The
rewrite loads PRISM once into cached float32 matrices and indexes them directly,
taking the full statewide simulation from impractical to **~20 seconds** for all
119,232 cell-years.

---

## 8. Modelling decisions the chapter leaves open

Recorded because they affect results and are choices, not deductions:

- **Foraging period.** Whether the 2 mating days come out of the 22-day longevity
  or precede it — see §5. The code takes the first reading.
- **No-egg-day attribution.** A day can be blocked by low temperature *and* high
  rain at once. Temperature- and precipitation-limited days are counted
  independently, so the two counts can sum to more than the number of blocked
  days. This matches the chapter's reported means closely (6.63 against 6.38,
  4.44 against 4.40), supporting the interpretation.
- **Offspring year offset.** Offspring produced in weather year *Y* are counted
  as the abundance of spring *Y+1*, so weather years 2008–2023 report
  reproductive success for 2009–2024, per Eq. 4.10 and the chapter's framing.
- **2017 forage gap.** The CDL forage summary is missing 1,452 Pennsylvania
  cells for 2017; these fall back to the nearest year for the same cell.

---

## 9. Reproducing these numbers

```bash
.venv/bin/python scripts/build_cache.py                       # once, ~2 min
.venv/bin/python scripts/simulate.py --list                    # what data is present
.venv/bin/python scripts/simulate.py --region pennsylvania
.venv/bin/python scripts/simulate.py --region pennsylvania --params calibrated
.venv/bin/python scripts/analyse_pa_simulation.py             # §1 tables
.venv/bin/python scripts/run_sobol.py --n 512                 # §4
.venv/bin/python scripts/make_figures.py
.venv/bin/python -m pytest tests/ -q
```

The marginal-vs-conditional R² decomposition in §2, the invariance and candidate
searches in §3, and the two-definition Sobol comparison in §4 were run as
one-off analyses and are not yet scripted — see `memory/` plan 2 follow-ups.
