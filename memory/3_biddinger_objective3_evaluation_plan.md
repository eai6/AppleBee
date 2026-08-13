# 3 — Objective 3 rebuilt on the Biddinger database  *(WITHDRAWN)*

> **Withdrawn 2026-08-13**, at the author's direction: the Biddinger data and the
> code built on it are removed from the repository, leaving Centrella and Turley
> as the only observation datasets. This plan is kept as the record of what was
> done and found — the files are recoverable from git history at `e5b2367`.
>
> The finding worth carrying forward is in §2b of `docs/REPLICATION_NOTES.md`:
> reconstructing Turley's own eight-farm sampling frame reproduced his published
> counts at r = 0.963, and the same frame over 13 years showed no detectable
> relationship.

**Date:** 2026-08-05
**Purpose:** Replace the six-point Turley evaluation of the full AppleBee model
with one fitted on the Biddinger *Osmia* database, so that Objective 3's R²
measures the model rather than a random intercept.

## Context

Plan 2 established that Objective 3's headline R² = 0.79 is an artefact: Eq. 4.11
is fitted on six annual counts at one site with a random intercept per year — one
observation per group, so the random effect is not identifiable and absorbs the
residuals. Fixed effects alone explain 21%, at p = 0.36. See §2 of
`docs/REPLICATION_NOTES.md`.

The Biddinger extract is the obvious remedy: 1,499 *Osmia* records over
2007–2025 against Turley's 183 over 2014–2019. Feasibility checks run while
writing this plan established what it can and cannot support.

### What the data actually gives us

**Geography — the important one.** The 40 distinct block coordinates collapse to
just **11 PRISM 4 km cells**, with 84 cell-years carrying at least one record.
Turley's single cell (1146, 240) is one of the 11. This is what makes the whole
exercise worthwhile: the evaluation gains a *spatial* dimension, so a random
intercept **by cell** has many years per group and is identifiable — exactly what
the year-effect in Eq. 4.11 is not. All 11 cells have forage-index coverage.

**Turley is not a subset of Biddinger, and neither contains the other.** They
share an ID scheme (`DJB YYYY-NNNN`) and farm names, but of Turley's 183 *Osmia*
IDs only **143 (78%) appear in Biddinger**, while **369 Biddinger blue-vane
records from 2014–2019 are absent from Turley**. They are overlapping curations
of the same collection program. **They must be merged by specimen ID, never
stacked** — stacking double-counts 143 specimens.

**Sampling effort is not constant, and this is the central obstacle.** Trap type
shifts from pan traps to blue vane around 2012:

| | 2007–2011 | 2012–2025 |
|---|---|---|
| Pan (`P`) | 180 | 0 |
| Blue vane (`V`) | 0 | 1,056 |

and collection programs rotate through the record (RAMP 2007–2009, SCRI
2010–2014, ICP 2015–2018, NRCS throughout, misc). Raw counts across that boundary
are not comparable.

**Zeros are ambiguous.** This is a specimen database: it records bees that were
caught. There are no zero-catch trap records, so a cell-year with no rows may
mean "sampled, none found" or "not sampled". Nothing in the extract distinguishes
them. `trap.no` is populated on 1,093 of 1,499 rows and only where a specimen was
caught, so it cannot serve as an effort denominator.

**The usable panel.** Restricting to blue vane and to cells with essentially
continuous coverage leaves three cells — (1145, 239), (1146, 239), (1146, 240) —
sampled every year from 2012 to 2024, with only two ambiguous zeros:

| cell | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 | 21 | 22 | 23 | 24 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (1145, 239) | 6 | 13 | 19 | 7 | 18 | 7 | 3 | 2 | **0** | 1 | 4 | 5 | 62 |
| (1146, 239) | 1 | 2 | 4 | 40 | 33 | 18 | 7 | 10 | 7 | 13 | 28 | 8 | **0** |
| (1146, 240) | 1 | 3 | 4 | 14 | 11 | 6 | 8 | 1 | 10 | 7 | 7 | 7 | 56 |

**39 cell-years against Turley's 6**, with 13 observations per group for the cell
random effect. The other six blue-vane cells are episodic — (1148, 237) and
(1149, 237) appear only in 2015–2017, (1144, 239) and (1144, 240) only in
2012–2014 — and enter only through the sensitivity variants below.

**Species.** *cornifrons* — the species the model is actually parameterised for —
has 517 records overall and 281 in the blue-vane subset across 36 cell-years.
That is enough to make *cornifrons* the primary response, which is a genuine
improvement on the chapter: it used genus counts because *cornifrons* was too
sparse in Turley alone.

**Weather and forage coverage bound the window.** Forage runs 2008–2023 and
weather to 2024-07-01, so weather years 2008–2023 give offspring years 2009–2024.
Biddinger's 2007–2008 observations and all of 2025 fall outside and are dropped
unless the forage series is extended.

## Approach

The honest framing is that **effort cannot be recovered, so it must be held
constant by restriction rather than modelled away.** Every design below follows
from that.

### Phase 1 — loader

New `applebee/evaluation/biddinger.py`, mirroring `turley.py`:

- [ ] Parse `Lat.Block(DD)` / `Long.Block(DD)` — stored as text with a degree
      suffix (`39.958620°`). Fall back to `lat.trap` / `long.trap`, which are
      dirtier: 1,108 non-null but containing zeros and a sign-flipped longitude
      (`77.3532` where `-77.3532` is meant). Reject anything outside the PA
      bounding box; 1,483 of 1,502 rows survive.
- [ ] Map each coordinate to a PRISM cell with the existing `nearest_cell`
- [ ] Coerce `Year` (one row holds the string `Unkn`)
- [ ] Merge with Turley by specimen ID, keeping the union and recording the
      overlap count so double-counting is impossible to introduce silently
- [ ] Emit a tidy frame: `specimen_id, cell, year, species, trap_type, program,
      farm, date_set, lat, lon`

### Phase 2 — the analysis panel

- [ ] Build the cell-year panel with an explicit `sampled` flag, derived from
      whether *any* record exists for that cell-year in the merged database —
      and document that this conflates "unsampled" with "sampled, caught
      nothing"
- [ ] Primary panel: blue vane only, the three continuously-sampled cells,
      offspring years 2012–2024 → 39 observations
- [ ] Response: ***Osmia* genus count first**, matching the chapter so the
      comparison against its 0.79 is apples-to-apples; then *cornifrons* alone
      as the second fit, since that is the species the model is parameterised
      for. Both reported, genus leading.
- [ ] Drop the two ambiguous zeros from the primary fit and report the fit with
      them retained as zeros as a sensitivity

### Phase 3 — fit and report

- [ ] Fit `observed ~ predicted` with a random intercept **by cell** (13 obs per
      group, identifiable) — not by year
- [ ] **Report marginal and conditional R² side by side, always.** This is the
      whole point of the exercise; a conditional-only number would repeat the
      original mistake
- [ ] Keep the weather-year offset: adults counted in spring Y come from weather
      year Y−1 (`OFFSPRING_YEAR_OFFSET`)
- [ ] Counts are overdispersed and bounded below at zero — fit a negative
      binomial GLMM alongside the Gaussian LME and report both, since a Gaussian
      fit to counts ranging 0–62 is not defensible on its own

### Phase 4 — sensitivity and write-up

- [ ] Vary: species (cornifrons / genus), panel (3 cells / all 9 blue-vane cells
      / all 11 cells), trap types (V only / all), and the ambiguous-zero rule
- [ ] Report the grid of marginal R² across those variants. If the result only
      holds in one corner, say so
- [ ] Re-fit the Turley six-point evaluation the same way and put the two
      side by side in `docs/REPLICATION_NOTES.md` §2
- [ ] Add tests for coordinate parsing, the ID merge, and the panel construction

### Phase 5 — stretch: validate the emergence sub-model

The emergence date sub-model has **never been evaluated against data** — it
carries 0.002% random-forest importance in Objective 4 and no observational
check anywhere in the chapter. Biddinger has dates, so this is newly possible.

A first pass comparing predicted emergence DOY to the earliest *cornifrons*
capture across 29 cell-years gives r = 0.23 (p = 0.22), with observed first
capture running **10–41 days earlier than predicted** in almost every cell-year
(predicted 110–130; observed 84–116).

That looks like a large negative bias in Eq. 4.1, **but the test as constructed
cannot establish it.** The date column is `Date set trap` — when the trap was
deployed, not when the bee was caught. A specimen was captured somewhere between
deployment and collection, so the earliest deployment date is a lower bound
biased early by whenever trapping happened to start, and 891 of 1,483 records
have an April deployment date regardless of year.

- [ ] Attempt it properly only if trap collection dates can be obtained
      (see the open question below); otherwise restrict to cell-years where
      deployment clearly precedes any plausible emergence, and report the
      year-to-year *correlation* rather than the absolute bias

## Decisions taken

- **Restriction over effort modelling.** Effort is only observable where a
  specimen was caught, so any effort covariate built from this extract is
  circular. Holding trap type, cells and program roughly constant by restriction
  costs sample size but is the only defensible option.
- **Random intercept by cell, not by year.** Fixing the exact flaw plan 2 found.
- **Merge with Turley by ID, keep the union.** Neither source dominates; the
  union is 40 specimens larger than Biddinger alone in the overlap window.
- **Genus first, then *cornifrons*.** *Osmia* genus counts lead, so the new
  result is directly comparable with the chapter's 0.79; *cornifrons* alone
  follows as the sharper test of a model parameterised for that species.
  (User decision, 2026-08-05.)
- **No trap-level effort records are available** — this extract is what exists
  (user decision, 2026-08-05). The restriction design is therefore the design,
  not a fallback, and the 45 cell-years it discards stay discarded. The loader
  should still keep effort columns in the tidy frame so the decision is
  revisitable.

## Open questions

1. ~~Trap-level effort records~~ — resolved: not available.
2. **Collection dates** for Phase 5, as distinct from `Date set trap`. Without
   them the emergence check cannot separate bee phenology from trap deployment.
3. **Is the 2025 spike real?** 229 records in 2025 against a 2007–2024 mean of
   ~70, and 153 of the 158 *cornifrons* are 2025. Worth confirming before it
   drives anything — it falls outside the forage window anyway.

## Plan

- [x] Phases 1–4 as above
- [ ] Phase 5 only if question 2 resolves

## Progress / outcome

Phases 1–4 built and run. Full write-up is §2b of `docs/REPLICATION_NOTES.md`.

### The result

**AppleBee's predicted offspring has no detectable relationship with observed
*Osmia* abundance on the larger panel, and the slope is negative.**

| Response | n | cells | marginal R² | conditional R² | slope | p |
|---|---|---|---|---|---|---|
| *Osmia* genus | 37 | 3 | 0.008 | 0.008 | −0.219 | 0.54 |
| *O. cornifrons* | 37 | 3 | 0.035 | 0.095 | −0.182 | 0.44 |
| Turley (chapter) | 6 | 1 | 0.212 | 0.803 | +1.994 | 0.001 |

Robust across all eight variants of species × cell set × ambiguous-zero rule:
marginal R² never exceeds 0.084, slope negative in every one, best p = 0.09.

The decisive check is **Turley's own cell extended from 6 years to 13**: same
site, same trap type, same response. r goes from +0.46 (chapter, n=6) to −0.25
(n=13). Re-curating the *same six years* from the merged database already drops
it to +0.31, p = 0.55. The original correlation survives neither more years nor
a different curation of the same specimens.

### What was built

- `applebee/evaluation/biddinger.py` — loader, cell assignment, panel
  construction, LME with cell random intercept, marginal/conditional R² helper
  that returns both so neither can be quoted alone
- `scripts/run_biddinger_evaluation.py` → `outputs/tables/objective3b_*.csv`
- `tests/test_biddinger.py` — 11 tests: coordinate parsing, the species/trap/
  cell filters, the ambiguous-zero rule, and the ID merge

### Things found along the way

- **The Turley merge is a union, not a concatenation** — 143 shared IDs, 40
  Turley-only added, 369 Biddinger-only in the overlap window. Concatenating
  would have double-counted 143 bees. Pinned by a test.
- **One duplicate specimen ID in the extract**: `DJB 2024-02023` appears as two
  *O. bucephala* from different farms on different dates. Both rows are kept —
  they are two physical bees with a label clash — and surfaced through
  `BiddingerData.duplicate_ids`. A test pins the count so a new collision fails
  the suite. Found because the test suite asserted uniqueness and it did not
  hold.
- **A real zero and an unsampled year are now distinguished** where the data
  allows it: *pumila* present but no *cornifrons* proves the cell was sampled,
  so `cornifrons == 0` is genuine and survives the filter. Only cell-years with
  no genus records at all are ambiguous, and there are just two.

### Decisive version: Turley's own 8-farm sampling frame, extended to 13 years

Turley trapped at exactly eight farms — the four FREC Rouzer plots, FREC pears,
Pulig-Cherryvale, Scott Slaybaugh North and South. All eight are in the Biddinger
database. Restricting the merged record to those eight plus blue vane reproduces
his sampling frame, then runs it for 13 years instead of 6.

**It validates**: over 2014–2019 the reconstruction correlates with Turley's
published annual counts at **r = 0.963**, matching exactly in 2015 (58), 2018
(27) and 2019 (15). The frame is right.

| Treatment | n | r | R² | p |
|---|---|---|---|---|
| *Osmia*, prediction at Turley's cell | 13 | −0.121 | 0.015 | 0.69 |
| *Osmia*, prediction averaged over 3 cells | 13 | −0.191 | 0.037 | 0.53 |
| *cornifrons* | 13 | −0.175 | 0.031 | 0.57 |
| *Osmia*, excluding the 2024 spike | 12 | **+0.005** | 0.000 | 0.99 |
| *Osmia* per active farm (effort-normalised) | 13 | −0.185 | 0.034 | 0.54 |
| well-sampled years only (≥6 of 8 farms) | 9 | **−0.036** | 0.001 | 0.93 |

Every treatment converges on zero, including the two that answer the obvious
objections — normalising by active farms, and dropping thin years. Effort is not
itself correlated with the prediction (r = −0.31, p = 0.30), so the null is not
an effort artefact. This is the strongest statement the data supports:
**Turley's six points reproduce, and the same sampling frame over 13 years shows
nothing.**

### Also checked: FREC only, blue vane only

Narrowing to the twelve FREC farms at the Penn State Fruit Research and Extension
Center — one research station, one trap type — removes farm turnover as a
confound and gives an **unbroken 2012–2025 series**, 13 usable years once
trimmed to the forage window.

| Response | n | r | R² | p |
|---|---|---|---|---|
| *Osmia* genus | 13 | −0.230 | 0.053 | 0.45 |
| *cornifrons* | 13 | −0.139 | 0.019 | 0.65 |
| *Osmia*, excluding the 2024 spike | 12 | **+0.028** | 0.001 | 0.93 |
| Spearman rank, *Osmia* | 13 | −0.132 | — | 0.67 |

Stable across both parameter sets and both FREC cells: eight variants, R² from
0.005 to 0.053, negative slope in every one, p ≥ 0.45 throughout. Removing the
one outlying year leaves r = +0.03 — the absence of a relationship, not a weak
one.

2017 and 2018 carry the two lowest predicted values in the series (1.60 and 2.43
against a mean of 7.8) yet both observed 16 *Osmia*, mid-range. The model's
sharpest predictions are the ones the data contradicts most clearly.

Still uncontrolled: trapping *intensity* at FREC, which is not recorded. This
controls location, trap type, program and curation — as far as the data allows.

### Correction to this plan's own premise

The Context section above claims the extract's value is that it "gains a
*spatial* dimension". Investigating the data further shows that is **half
right, and the weaker half was overstated**:

- **The identifiability gain is real.** Many years per cell makes the cell
  random intercept estimable, unlike the chapter's year effect.
- **The spatial information gain is small.** The three primary cells are 4–8 km
  apart and their daily temperatures correlate at **r = 0.9995–0.9999**. They
  receive the same emergence date, favourable-day count and mortality to within
  rounding. The *entire* between-cell difference in predicted offspring is one
  binary flag — whether the forage index clears `L_H = 0.5`, giving 2 eggs/day
  against 1 — and the cell that clears it averages 0.514, straddling the
  threshold: it drops to 1 egg/day in 2021 and 2022 and sits at exactly 0.500 in
  2023.

So Objective 3b remains fundamentally a **temporal** test with a factor-of-two
multiplier on one of three cells. This explains why conditional R² equals
marginal R² to four decimals in the genus fit — there is almost nothing for the
cell effect to absorb. It does not change the null result, but it does mean a
genuine spatial test needs cells far enough apart to have different weather, and
none exist in this database.

Also relevant, and newly established: **the extract contains only one genus.**
All 1,499 records are *Osmia*, six species. So catch cannot be normalised
against total bee catch — the standard way round unknown trapping effort is
unavailable. Turley carries all 30 genera but only for 2014–2019 at one site.

### What this does not establish

The negative result is about the *evaluation*, not the model. Three confounds
remain open and none can be closed with what exists: effort is still
uncontrolled within the restriction; blue vane catch measures foraging adults
and may be anti-correlated with the forage index that drives the model; and
genus counts pool species with different phenology (restricting to *cornifrons*
roughly quadruples marginal R², the only hint that this matters).

## Commits

| SHA | Date | Subject |
|---|---|---|
| `e5b2367` | 2026-08-08 | Evaluate Objective 3 on the Biddinger Osmia database |

## Follow-ups

- **Plan 4 — separate model failure from evaluation failure.** The negative
  result is only actionable once the three confounds in §2b can be told apart.
  Cheapest first step: test confound 2 directly by regressing blue-vane catch on
  the forage index alone. If catch is genuinely anti-correlated with forage,
  blue vane cannot validate this model at all and the whole objective needs a
  different response variable.
- **A spatially informative evaluation needs data from outside Adams County.**
  Every usable cell here shares weather to r > 0.999, so the model's spatial
  predictions are untested. Turley's 2024 supplement
  (`archives/Python_scripts/data/saae014_suppl_supplementary_materials/`) holds
  a 2021–2022 collections dataset and an iNaturalist extract — worth checking
  whether either reaches beyond this one county.
- **Trap-level effort records remain the highest-value external input**, even
  though they are unavailable now (user, 2026-08-05). They would turn 45
  discarded cell-years into usable ones and make the null result interpretable.
  Worth re-asking if the Biddinger lab's raw collection log ever surfaces.
- **Phase 5 (emergence validation) is still blocked** on collection dates as
  distinct from `Date set trap`. Now more interesting than before: if the full
  model has no signal, checking whether its *first* sub-model does is the
  natural way to localise the failure.
- The foraging-period ambiguity (plan 2, §5 of the notes) shifts every predicted
  offspring count by ~11%. A slope absorbs it, so it does not explain the null,
  but it should be settled before any coefficient is interpreted.
- Consider a negative-binomial fit as the headline rather than a sensitivity —
  `fit_negbin` exists but is not yet reported. Counts spanning 0–62 with a
  Gaussian LME is defensible only because the conclusion is a null.
