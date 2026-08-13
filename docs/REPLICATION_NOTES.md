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
| 3b — full model vs Biddinger, larger panel | — | marginal R² 0.02–0.08, slope negative | open — see §2b |
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

**The chapter's 0.79 is reproducible and is what its stated method produces.**
Which of these two R² definitions should be reported is a question for a
statistician; §2b records the same comparison on a panel with replication, which
is the evidence most useful to that conversation.

The same decomposition on Objective 2, where the random effect *is* identifiable
(51 observations, 17 sites × 3 time points): marginal R² 0.175, conditional
0.410. Less extreme, but the reported figure is still mostly the site intercept.

**This motivates adding the Biddinger database** (1,499 *Osmia*
records, 2007–2025, 63 farms) — it replaces six points with enough data for the
evaluation to mean something. That evaluation is now built; see §2b.

---

## 2b. Objective 3 on the Biddinger database — a panel with replication

`applebee/evaluation/biddinger.py`, run by `scripts/run_biddinger_evaluation.py`.

The Biddinger *Osmia* extract covers 2007–2025 across **11 PRISM cells** rather
than 2014–2019 across one, which is what makes a defensible fit possible: with
many years per cell, a random intercept **by cell** is identifiable.

### What the extract contains

**One genus.** All 1,499 identified records are *Osmia* (Megachilidae), across
six species: *pumila* 546, ***cornifrons* 517**, *bucephala* 231, *taurus* 165,
*georgica* 21, *lignaria* 19. Three rows carry no determination.

This has a consequence worth stating plainly: because no other genus is present,
**catch cannot be normalised against total bee catch**. That standard escape from
unknown trapping effort — express *Osmia* as a share of everything caught — is
not available here. Turley's dataset does carry all 30 genera, but only for
2014–2019 at one site.

**Two locations, one of them negligible.** All records are Pennsylvania: 1,488
from **Adams County** and 11 from **Centre County**, 105 km apart.

| Cell | County | lat, lon | n | farms | years | species |
|---|---|---|---|---|---|---|
| (1145, 239) | Adams | 39.948, −77.293 | 490 | 20 | 2007–2025 | 6 |
| (1146, 239) | Adams | 39.946, −77.258 | 306 | 13 | 2008–2023 | 6 |
| (1146, 240) | Adams | 39.937, −77.250 | 190 | 8 | 2011–2025 | 6 |
| (1149, 237) | Adams | 40.045, −77.134 | 186 | 6 | 2007–2018 | 6 |
| (1144, 239) | Adams | 39.976, −77.322 | 115 | 6 | 2008–2025 | 5 |
| (1148, 237) | Adams | 40.042, −77.172 | 90 | 1 | 2015–2017 | 4 |
| (1145, 238) | Adams | 40.001, −77.283 | 46 | 4 | 2007–2013 | 6 |
| (1144, 240) | Adams | 39.900, −77.352 | 39 | 1 | 2011–2014 | 5 |
| (1143, 241) | Adams | 39.869, −77.371 | 19 | 4 | 2009–2012 | 2 |
| (1130, 219) | Centre | 40.780, −77.898 | 8 | 2 | 2007–2008 | 2 |
| (1131, 220) | Centre | 40.756, −77.876 | 3 | 1 | 2007–2008 | 3 |

62 named farms in total, at 40 distinct block coordinates. The nine Adams cells
sit inside a **22 × 22 km** box centred on the Penn State Fruit Research and
Extension Center; the two Centre County cells hold 11 specimens from 2007–2008
and drop out of every analysis window.

### The "spatial" dimension is thinner than the cell count suggests

The cell count makes the panel look spatially replicated. In terms of what the
model can *see*, it is not.

Daily mean temperature across the three primary cells correlates at
**r = 0.9995–0.9999** — they are 4–8 km apart, so PRISM gives them effectively
the same weather. Every cell therefore receives the same emergence date, the same
favourable-day count and the same mortality, to within rounding.

The entire between-cell difference in predicted offspring comes from **one binary
flag**: whether the forage index clears `L_H = 0.5`, which sets 2 eggs/day against
1. And the cell that clears it does so by a hair:

| Year | (1145, 239) | (1146, 239) | (1146, 240) |
|---|---|---|---|
| 2012 | 0.544 → **2/day** | 0.450 → 1/day | 0.403 → 1/day |
| 2015 | 0.516 → **2/day** | 0.409 → 1/day | 0.406 → 1/day |
| 2019 | 0.509 → **2/day** | 0.403 → 1/day | 0.406 → 1/day |
| 2021 | 0.494 → 1/day | 0.406 → 1/day | 0.406 → 1/day |
| 2022 | 0.497 → 1/day | 0.400 → 1/day | 0.406 → 1/day |
| 2023 | 0.500 → **2/day** | 0.409 → 1/day | 0.400 → 1/day |

(1145, 239) averages 0.514 against 0.417 and 0.406 for the others, and straddles
the threshold — it flips to 1 egg/day in 2021 and 2022, and in 2023 sits exactly
on 0.500. So Objective 3b is **still fundamentally a temporal test**, with a
factor-of-two multiplier applied to one of three cells by a step function whose
input moves by 0.05 across the whole panel.

This does not change the null result — it explains why the cell random effect
absorbs so little (conditional R² equals marginal R² to four decimals for the
genus fit) and it means the identifiability gain is real while the spatial
information gain is small. A genuine spatial test needs cells far enough apart to
have different weather.

Three properties of the source constrain the design.

- **It is a specimen database, not a survey.** Only bees that were caught are
  recorded, so a cell-year with no rows may mean "sampled, caught nothing" or
  "not sampled". Trap-level effort records are not available, so effort is held
  constant by *restriction* — blue vane only, cells sampled continuously —
  rather than modelled away.
- **Trap type changes.** Pan traps run 2007–2011 (180 records), blue vane
  2012–2025 (1,056), with no overlap. Mixing them confounds trap type with year.
- **It overlaps Turley without containing it.** Both use the `DJB YYYY-NNNN`
  scheme, but 40 of Turley's 183 *Osmia* are absent here and 369 of these are
  absent from Turley. They are merged on specimen ID — concatenating them would
  double-count 143 bees.

The primary panel is blue vane at the three continuously sampled cells
(1145, 239), (1146, 239) and (1146, 240), giving **37 cell-years against the
chapter's 6**:

| Response | n | cells | marginal R² | conditional R² | slope | p |
|---|---|---|---|---|---|---|
| *Osmia* genus (as the chapter counts) | 37 | 3 | **0.008** | 0.008 | −0.219 | 0.54 |
| *O. cornifrons* alone | 37 | 3 | **0.035** | 0.095 | −0.182 | 0.44 |
| Turley 2014–2019 (chapter Objective 3) | 6 | 1 | 0.212 | 0.803 | +1.994 | 0.001 |

**AppleBee's predicted offspring has no detectable relationship with observed
*Osmia* abundance, and the slope is negative.** This is not an artefact of one
restriction choice — it holds across all eight variants of species, cell set and
ambiguous-zero rule:

| Response | cells | zeros | n | marginal R² | slope | p |
|---|---|---|---|---|---|---|
| genus | 3 continuous | drop ambiguous | 37 | 0.008 | −0.219 | 0.54 |
| genus | 3 continuous | keep as zero | 39 | 0.008 | −0.219 | 0.58 |
| genus | all sampled | drop ambiguous | 52 | 0.015 | −0.383 | 0.39 |
| genus | all sampled | keep as zero | 143 | 0.020 | −0.172 | 0.37 |
| cornifrons | 3 continuous | drop ambiguous | 37 | 0.035 | −0.182 | 0.44 |
| cornifrons | 3 continuous | keep as zero | 39 | 0.034 | −0.178 | 0.46 |
| cornifrons | all sampled | drop ambiguous | 52 | 0.084 | −0.341 | 0.09 |
| cornifrons | all sampled | keep as zero | 143 | 0.039 | −0.113 | 0.16 |

Marginal R² never exceeds 0.084 and the slope is negative in every one.

The cleanest single check is **Turley's own cell, extended from 6 years to 13**.
Same site, same trap type, same response — only more years:

| | n | r | R² | p |
|---|---|---|---|---|
| 2014–2019, Turley's curation (the chapter) | 6 | +0.46 | 0.212 | 0.36 |
| 2014–2019, merged curation of the same specimens | 6 | +0.31 | 0.098 | 0.55 |
| **2012–2024, merged** | **13** | **−0.25** | **0.062** | **0.41** |

The original correlation does not survive either more years *or* a different
curation of the same six years. Pooling to statewide annual means gives the same
answer: r = −0.14 (p = 0.65) over 13 years, and +0.12 (p = 0.70) with the 2024
spike removed.

### The decisive design: Turley's own sampling frame, extended to 13 years

Turley et al. trapped at exactly **eight farms** across four blocks — the four
FREC Rouzer plots, FREC pears, Pulig-Cherryvale, and Scott Slaybaugh North and
South. All eight are present in the Biddinger database. Restricting the merged
record to those eight farms and to blue vane reproduces Turley's sampling frame
exactly, and then runs it for 13 years instead of 6.

**The reconstruction validates against the published series.** Over the 2014–2019
overlap it correlates with Turley's own annual *Osmia* counts at **r = 0.963**,
matching exactly in three of the six years:

| Year | reconstructed | Turley published |
|---|---|---|
| 2014 | 19 | 10 |
| 2015 | **58** | **58** |
| 2016 | 58 | 47 |
| 2017 | 33 | 26 |
| 2018 | **27** | **27** |
| 2019 | **15** | **15** |

So the frame is right. Extending it:

| Year | *Osmia* | *cornifrons* | farms active | predicted |
|---|---|---|---|---|
| 2012 | 4 | 0 | 3 | 14.56 |
| 2013 | 5 | 1 | 3 | 8.86 |
| 2014 | 19 | 0 | 7 | 11.57 |
| 2015 | 58 | 26 | 7 | 14.08 |
| 2016 | 58 | 16 | 8 | 14.32 |
| 2017 | 33 | 10 | 8 | **2.72** |
| 2018 | 27 | 4 | 8 | **3.00** |
| 2019 | 15 | 5 | 5 | 12.43 |
| 2020 | 17 | 11 | 4 | 10.94 |
| 2021 | 21 | 11 | 6 | 15.60 |
| 2022 | 39 | 34 | 6 | 5.71 |
| 2023 | 20 | 3 | 6 | 9.84 |
| 2024 | 89 | 31 | 6 | 5.95 |

| Treatment | n | r | R² | p |
|---|---|---|---|---|
| *Osmia*, prediction at Turley's cell | 13 | −0.121 | 0.015 | 0.69 |
| *Osmia*, prediction averaged over the 3 cells | 13 | −0.191 | 0.037 | 0.53 |
| *cornifrons* | 13 | −0.175 | 0.031 | 0.57 |
| *Osmia*, excluding the 2024 spike | 12 | **+0.005** | 0.000 | 0.99 |
| *Osmia* per active farm (effort-normalised) | 13 | −0.185 | 0.034 | 0.54 |
| *Osmia*, well-sampled years only (≥6 of 8 farms) | 9 | **−0.036** | 0.001 | 0.93 |
| Spearman rank, *Osmia* | 13 | −0.245 | — | 0.42 |

**Every treatment converges on zero**, including the two that address the obvious
objections: normalising by the number of active farms, and dropping the
thinly-sampled years. Sampling effort is not itself correlated with the
prediction (farms active vs predicted: r = −0.31, p = 0.30), so the null is not
an effort artefact.

The chapter's 2017 and 2018 remain the sharpest contradiction. They carry the two
lowest predicted values in the whole series — 2.72 and 3.00 against a mean of
9.2 — with all eight farms active, and they observed 33 and 27 *Osmia*, both
above the 13-year median. The model's most confident predictions are the ones the
data contradicts most clearly.

**Summary.** Turley's published six points reproduce, and the reconstruction of
his own sampling frame reproduces them at r = 0.963. Running that same frame for
13 years leaves no detectable relationship. Whether that overturns the six-point
result, or simply reflects trapping effort the data cannot control for, is part
of the open question in §2.

### Also checked: FREC only, blue vane only

Every restriction so far still mixes farms. Narrowing to the **twelve FREC farms
at the Penn State Fruit Research and Extension Center** — one research station,
one trap type — removes farm turnover as a confound entirely and yields an
unbroken 2012–2025 series. Trimming to years the forage index covers gives 13
consecutive years at a single PRISM cell:

| Year | *Osmia* | *cornifrons* | predicted offspring |
|---|---|---|---|
| 2012 | 2 | 0 | 11.57 |
| 2013 | 5 | 1 | 6.75 |
| 2014 | 15 | 0 | 7.83 |
| 2015 | 34 | 18 | 10.77 |
| 2016 | 25 | 9 | 11.54 |
| 2017 | 16 | 4 | 1.60 |
| 2018 | 16 | 4 | 2.43 |
| 2019 | 12 | 3 | 8.85 |
| 2020 | 17 | 11 | 8.14 |
| 2021 | 19 | 11 | 11.70 |
| 2022 | 35 | 32 | 5.86 |
| 2023 | 15 | 3 | 9.49 |
| 2024 | 70 | 29 | 4.45 |

| Response | n | r | R² | p |
|---|---|---|---|---|
| *Osmia* genus | 13 | −0.230 | 0.053 | 0.45 |
| *cornifrons* | 13 | −0.139 | 0.019 | 0.65 |
| *Osmia*, excluding the 2024 spike | 12 | **+0.028** | 0.001 | 0.93 |
| *cornifrons*, excluding 2024 | 12 | +0.026 | 0.001 | 0.94 |
| *Osmia*, Spearman rank | 13 | −0.132 | — | 0.67 |

Stable across both parameter sets and both FREC cells — eight variants give R²
between 0.005 and 0.053, a negative slope in every one, and p ≥ 0.45 throughout.
Excluding the single outlying year leaves a correlation of **+0.03**: not a weak
relationship, but the absence of one.

The chapter's 2017 and 2018 are instructive. They carry the two lowest predicted
values in the series (1.60 and 2.43, against a mean of 7.8) yet both observed 16
*Osmia* — squarely mid-range. The model's sharpest predictions are contradicted
most clearly.

This does not control trapping *intensity* at FREC, which may still vary between
years and is not recorded. It does control location, trap type, program and
curation, which is as far as the data allows.

### What this does and does not establish

It establishes that **the chapter's Objective 3 result is not reproducible on a
larger sample from the same monitoring program**, and that its R² = 0.79 was
carried by a random effect fitted to one observation per group.

It does not establish that AppleBee is wrong. Three alternative explanations
remain open, and none can be closed with the data available:

1. **Effort is still uncontrolled.** Restriction holds trap type and cell
   constant but not trapping intensity, which varies between cells and years in
   ways the extract cannot show. This is the most likely confound and the reason
   trap-level effort records would be worth more than any modelling change.
2. **Blue vane catch is not abundance.** It samples foraging adults, and catch
   depends on trap attractiveness relative to competing floral resources —
   plausibly *anti*-correlated with the forage index that drives egg production
   in the model, which would explain a negative slope.
3. **Genus counts pool species.** *pumila*, *bucephala* and *taurus* have
   different phenology from the modelled species. Restricting to *cornifrons*
   roughly quadruples marginal R² (0.008 → 0.035, and 0.015 → 0.084 on the wider
   panel) and gives the only variant approaching significance, which is weak
   support for this mattering.

A defensible evaluation of the full model still does not exist. Objectives 2 and
3 both now rest on data limitations rather than on the model.

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

## 4. The Sobol ranking flip is real and is *not* caused by the §3 data gap

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
.venv/bin/python scripts/run_pa_simulation.py --params default
.venv/bin/python scripts/run_pa_simulation.py --params calibrated
.venv/bin/python scripts/analyse_pa_simulation.py             # §1 tables
.venv/bin/python scripts/run_sobol.py --n 512                 # §4
.venv/bin/python scripts/run_biddinger_evaluation.py          # §2b
.venv/bin/python scripts/make_figures.py
.venv/bin/python -m pytest tests/ -q
```

The marginal-vs-conditional R² decomposition in §2, the invariance and candidate
searches in §3, and the two-definition Sobol comparison in §4 were run as
one-off analyses and are not yet scripted — see `memory/` plan 2 follow-ups.
