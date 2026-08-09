# 2 — Replication diagnosis and data organisation

**Date:** 2026-08-05
**Purpose:** Pin down exactly which chapter results do *not* replicate and why;
verify the defect list attributed to the archived code; and reorganise the
simulation's input data into one reviewable folder under `data/`, as
preparation for adding new datasets.

## Context

`docs/REPLICATION_NOTES.md` already states an overall verdict — Objectives 3 and
4 replicate, Objective 2 does not — but it was written alongside the rewrite, so
its claims are self-reported. Three things are unresolved:

1. **Which numbers actually fail, and by how much**, separated from numbers that
   merely differ in the third decimal. The notes mix both in one table.
2. **Whether the eight defects blamed on the archived code are real.** Each needs
   to be pointed at the specific line in `archives/` and, where it changes a
   result, quantified.
3. **What data the simulation actually reads.** The inputs are scattered across
   `archives/output/`, `archives/data/`, `archives/research/data/` and
   `archives/Python_scripts/data/` — and `.gitignore:12-14` excludes all four
   from version control, so the actual model inputs are untracked and
   unreviewable.

### What the code reads today

Traced from `applebee/config.py:26-41` and the two evaluation modules:

| Input | Path | Size | Read by |
|---|---|---|---|
| PA daily mean temp | `archives/output/tmean_prism_pennsylvania_data_1990_2023.csv` | 1.5 G | `weather.load_weather` → all of Obj. 3/4 |
| PA daily precipitation | `archives/output/ppt_prism_pennsylvania_data_1990_2023.csv` | 805 M | same |
| PA spring forage index | `archives/data/forage.csv` | 6.7 M | `forage.ForageGrid.load` |
| NY daily mean temp | `archives/output/tmean_prism_new_york_data.csv` | 24 K | `evaluation/centrella.py` |
| NY daily precipitation | `archives/output/ppt_prism_new_york_data.csv` | 16 K | `evaluation/centrella.py` |
| NY site forage index | `archives/research/data/Centrella_Spring_Forage_2015.csv` | 4 K | `evaluation/centrella.py` |
| Centrella observations | `archives/research/data/Centrella_et_al_Data.csv` | 44 K | `evaluation/centrella.py` (Obj. 2) |
| Turley observations | `archives/Python_scripts/data/doi_10_5061_dryad_9kd51c5mc__v20220727/Turley_et_al_ECOEVO_blue_vane_bee_collection_data.csv` | 2.7 M | `evaluation/turley.py` (Obj. 3) |

Derived, not source: `data/cache/*.npy|parquet` (717 M) is the parsed PRISM
matrices, rebuilt by `scripts/build_cache.py`.

### New data waiting to be added

`data/raw/Biddinger Bee Database, Osmia 080825.xlsx` — 1,499 *Osmia* specimen
records (one sheet, "Edward, Osmia"; the 120,832-row frame is mostly trailing
blanks). Coverage:

- **2007–2025**, mostly Adams County PA (1,488 of 1,499 rows), 63 farms,
  5 collection programs (NRCS, ICP, SCRI, RAMP, misc)
- Species: *pumila* 546, **cornifrons 517**, *bucephala* 231, *taurus* 165, plus
  *georgica* and *lignaria*
- Trap-level coordinates on 1,108 rows, block-level on 1,489

This is a direct superset in time of the Turley et al. (2022) evaluation the
chapter uses for Objective 3 (2014–2019, one site, 6 points). It should support a
much stronger Objective 3, but that is **plan 3** — this plan only gets the data
organised and characterised.

## Plan

### A. Diagnose what does not replicate

- [x] Re-run every objective from a clean state and capture the numbers, rather
      than trusting the notes
- [x] Classify each chapter-vs-replication comparison as **matches**,
      **differs but consistent**, or **fails**, with a stated tolerance
- [x] For each failure, isolate the cause to one of: input data gap, an
      ambiguity in the chapter, or a defect in either implementation
- [x] Objective 2 specifically: exhaust the candidate derivations of the
      observed egg counts against the chapter's 206 / 65 / 12 / 42 target and
      record what the residual gap implies
- [x] Objective 2 Sobol: determine whether the parameter-ranking flip is caused
      by the observed-egg gap or is independent of it
- [x] Write findings into `docs/REPLICATION_NOTES.md`, replacing self-reported
      claims with reproducible ones

### B. Verify the errors attributed to the prior code

- [x] For each of the eight defects in §2 of the notes, cite the exact archived
      file and line
- [x] Mark each as **confirmed**, **overstated**, or **not a defect**
- [x] Quantify the ones that change a result (run the archived behaviour against
      the corrected behaviour where feasible)
- [x] Check for defects the notes missed

### C. Organise the simulation dataset

- [x] Create `data/inputs/` as the single reviewable location for everything the
      model reads
- [x] Copy the small inputs there outright; the two PA PRISM CSVs (2.3 GB total)
      are referenced rather than duplicated
- [x] Write `data/inputs/MANIFEST.md` — per file: role, provenance, which module
      reads it, which columns are used, shape and coverage
- [x] Point `applebee/config.py` at `data/inputs/` so `archives/` becomes a
      historical reference only
- [x] Characterise the Biddinger database and record what it would take to use
      it (deferred to plan 3)

## Decisions taken

- **The two PA PRISM CSVs are not duplicated into `data/inputs/`.** At 2.3 GB
  they cannot be tracked in git and copying them doubles disk for no review
  value — a 12,000-column wide CSV is not something to read by eye. They are
  referenced from their archive location and described in the manifest instead.
  Everything else (~9.5 MB total) is copied and is small enough to track.

## Progress / outcome

Full write-up is in `docs/REPLICATION_NOTES.md`, rewritten from the ground up.
Summary of what was established:

### A — what does not replicate

1. **Objective 3's R² = 0.79 reproduces but is an artefact.** Eq. 4.11 is fitted
   on six observations with a random intercept by year — one observation per
   group, so the random effect is not identifiable and its BLUP absorbs the
   residuals. Conditional R² 0.803, **marginal R² 0.212**, and plain OLS on the
   same six points gives R² 0.212 at **p = 0.36**. The best-replicating objective
   turns out to be the least informative one. This is the strongest argument for
   bringing in the Biddinger data.
2. **Objective 2's gap is provably a response-variable problem, not scaling.**
   R² is exactly invariant to affine transforms of the response — confirmed at
   0.3613 for emerged adults, adults × 1.42 and adults + 19.3. So no
   units/scale explanation is possible. An exhaustive search over derivations
   available in the extract found none reaching the chapter's 206/65/12/42 and
   **none exceeding R² 0.41**; the best distributional match (nest tubes × 9.6)
   scores *worse*, at 0.352. Widening the brood-failure correction plateaus at
   0.44. The chapter's minimum of 12 against a mean of 65 is the tell: it counts
   brood cells, not survivors.
3. **The Sobol ranking flip is independent of that gap, and now fully
   explained.** Re-run under both observed-egg definitions (1,280 evaluations
   each), temperature dominates either way (S1 0.59 and 0.66 against
   precipitation 0.14 and 0.09). Two further candidates were tested and
   rejected — the archived `<` vs `<=` operator (identical to four decimals,
   because the operators differ only on exact ties and Saltelli samples a
   continuum) and the sensitivity target (mean predicted eggs instead of R²
   moves the indices but not the ranking). The real reason is mechanical:
   across the Table 4-5 ranges, precipitation swings mean eggs by **0.8**
   against temperature's **4.2**, because 51% of days are already bone dry and
   pass at any threshold. Precipitation is structurally the *least* influential
   of the three, so the chapter's S1 = 0.38 is not reachable from the model as
   specified.
4. **Objective 4's mean and minimum are reconciled by one reading of the
   foraging period.** The chapter does not say whether the 2 mating days come
   out of the 22-day longevity or precede it. Foraging a full 22 days after
   mating moves the statewide mean from 15.44 to **17.05** and the minimum from
   0.00 to **0.71**, matching the chapter's 17 and 1 simultaneously. The code
   keeps the 20-day reading; the alternative is recorded.
5. **The chapter's winter-mortality example is impossible in its own window.**
   [15 Aug, 1 Oct) is 47 days, so at W_F = 0.0025 the ceiling is 11.75%, not the
   15% the chapter illustrates with 60 warm days. Simulation confirms
   `prewinter_warm_days` never exceeds 47 across 119,232 cell-years. The test
   suite pins the 60-day example with a synthetic array, so it passes without
   exposing this.

### B — the eight attributed defects

Seven confirmed as stated with file and line. Two corrections to the earlier
account, and one new defect it missed:

- **#4 is half wrong.** The precipitation comparison was genuinely wrong
  (`egg_production.py:62`), but the forage comparison was **already correct** —
  `egg_production.py:39-42` gives 2 eggs/day when `forage >= threshold`, exactly
  as Eq. 4.3 says. The rewrite changed nothing there.
- **#3 has an overstated sub-claim.** The looping and vectorised emergence paths
  do *not* disagree with each other except at exact equality; both return
  crossing-day + 1, wrong in the same direction by the same amount.
- **New defect, worse than #6.** `utils.py:8` loads the *forage* table from
  `tmean_prism_new_york_data.csv` — the temperature file — with the correct line
  commented out above it. `getGridForageQuality` at `:39` then queries a
  `sprng__` column on it and, on failure at `:41`, recurses on `year + 1` with
  no termination condition, so a miss recurses to `RecursionError`. That
  module's forage lookup could never have returned a valid value.

### C — data organisation

`data/inputs/` now holds everything the model reads:

```
data/inputs/
  MANIFEST.md      per-file role, provenance, consumer module, columns, coverage
  weather/         pa_tmean, pa_ppt (symlinks, 2.3 GB), ny_tmean, ny_ppt
  forage/          pa_forage_spring_lonsdorf.csv, ny_forage_spring_2015_sites.csv
  observations/    centrella_2020_ny_orchards.csv, turley_2022_pa_blue_vane.csv,
                   biddinger_osmia_pa_2007_2025.xlsx  (not yet used)
```

`applebee/config.py` points here; `archives/` is now historical reference only.
Tests pass and the statewide model reproduces its previous output after the
repoint. `.gitignore` gained the two PA symlinks (they would dangle in a clone)
and `data/raw/` (the drop box for files not yet described in the manifest).

Coverage recorded while building the manifest: PA weather 7,452 cells ×
12,601 days (1990-01-01 – 2024-07-01, no gaps, no NaN); PA forage 117,780
cell-years 2008–2023 with **2017 short by 1,452 cells**; forage index range
0.000–0.697, so the 0.5 threshold sits inside the realised distribution;
Turley has 26,716 specimen rows but only **183 *Osmia***, which is the six
numbers Objective 3 rests on.

## Files changed

- `docs/REPLICATION_NOTES.md` — rewritten
- `data/inputs/**` — new
- `applebee/config.py` — paths repointed, `BIDDINGER_XLSX` added
- `.gitignore` — PA symlinks and `data/raw/`

## Commits

| SHA | Date | Subject |
|---|---|---|
| `211ce79` | 2026-08-08 | Diagnose the replication and consolidate model inputs under data/inputs/ |

## Follow-ups

- **Plan 3 — integrate the Biddinger Osmia database.** Now the highest-value
  next step, because §2 of the notes shows Objective 3's headline number is
  carried by a random effect fitted on six points. 1,499 records over 2007–2025
  and 63 farms would let the evaluation be fitted on data that can actually
  support it. Needs: coordinate parsing (`Lat.Block(DD)` values carry a `°`
  suffix and are stored as text), a decision on whether to model *Osmia* genus
  counts or *cornifrons* alone, and handling of unequal sampling effort across
  programs and years — trap counts are not constant, so raw counts are not
  directly comparable year to year.
- **Script the one-off analyses.** The marginal-vs-conditional decomposition
  (§2), the invariance and candidate searches (§3) and the two-definition Sobol
  comparison (§4) were run ad hoc. They are the evidence for the main claims and
  should live in `scripts/` so the notes stay reproducible.
- **Decide what to do about the foraging-period ambiguity** (§5). The code keeps
  the 20-day reading; if the 22-day reading is right, every Objective 4 number
  shifts by about 11%.
- **Report marginal R² alongside conditional R²** everywhere, or stop using a
  random intercept where it is not identifiable.
- Obtaining the full Centrella et al. (2020) brood-cell counts remains the one
  external dependency for closing Objective 2 — §3 shows nothing in the current
  extract can substitute.
