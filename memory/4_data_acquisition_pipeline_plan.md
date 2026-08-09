# 4 — Data acquisition pipeline (PRISM + CDL → forage)

**Date:** 2026-08-06
**Purpose:** Make AppleBee able to acquire its own inputs, so the simulation
extent stops being fixed to Pennsylvania. Two pipelines: daily PRISM weather,
and the Lonsdorf spring forage index built from the USDA Cropland Data Layer.

## Context

Plan 3 and the evaluation notebook both hit the same wall: the repository has
weather and forage for **Pennsylvania only**.

| Region | Cells | Days | Period |
|---|---|---|---|
| Pennsylvania | 7,452 | 12,601 | 1990–2024 |
| New York | 17 (Centrella sites) | 61 | May–Jun 2015 |
| Virginia | 57 | 242 | Nov 2016 – Jun 2017 |

The Lonsdorf forage index exists for PA cells alone. Extending the simulation to
the Northeast needs both datasets built from source.

### How the existing PA inputs were made

Reconstructed from `archives/R_scripts/Process_CDL_To_SFRQ _PA.Rmd`, the
`foragesummary_*.csv` chunk files, and the EcoSpatial workshop the user pointed
to (<https://climateecology.github.io/ecospatial-workshop/>):

1. CDL GeoTIFF per state per year, EPSG:5070 (NAD83 Conus Albers), 30 m.
2. Reclassify CDL class → `floral_resources_spring_index` via
   `archives/data/CDL/cdl_reclass_koh.csv` (134 classes, Koh et al. 2016 expert
   values, range 0–0.699).
3. Buffer each PRISM 4 km cell centroid by 1/3/5 km **in the raster CRS**.
4. Area-weighted mean of the reclassified raster within each buffer.

The workshop notes beeshiny uses `exactextractr::exact_extract()`, which is why
the archived values differ slightly from a plain `terra::extract()`. The
`foragesummary_*.csv` files are chunked in 1,000-point batches, matching the
`pennsylvania_prism_grid_points_0_1000.csv` splits in
`archives/Python_scripts/notebooks/landscape.ipynb` — i.e. they were produced by
uploading grid points to the PSU beeshiny service in batches, not computed
locally.

### The method reproduces — validated before building

Reimplemented in Python (`rasterio` + `exactextract`, `frac` op dotted with the
Koh spring index) and checked against `archives/data/forage.csv` for 2021 on a
60-cell random sample:

| Radius | n | r | mean abs diff | max abs diff |
|---|---|---|---|---|
| 1 km | 59 | **0.9853** | 0.0150 | 0.0642 |
| 3 km | 60 | **0.9896** | 0.0107 | 0.0378 |
| 5 km | 60 | **0.9920** | 0.0090 | 0.0344 |

Residual differences are consistent with beeshiny running on a different CDL
vintage and its own extraction path. **This is close enough to treat the local
pipeline as equivalent.**

**One cell had to be excluded**, and it carries the key design lesson: cell
(1182, 245) at −75.75, 39.71 sits outside the *state-clipped* PA CDL raster, so
its buffer returned no pixels — yet `forage.csv` has a value for it, because
beeshiny used national coverage. **The pipeline must mosaic neighbouring states
rather than use per-state clips**, or every state border becomes a data hole. For
a multi-state Northeast run that matters at every interior boundary.

### Source services, both probed and working

- **PRISM** — `https://services.nacse.org/prism/data/get/us/4km/{var}/{YYYYMMDD}`
  returns a ~2 MB zip of `.bil` for the whole CONUS. No key needed. Their terms
  rate-limit repeated fetches of the same file, so the downloader must cache and
  skip what it already has.
- **CDL** — `https://nassgeodata.gmu.edu/axis2/services/CDLService/GetCDLFile?year={Y}&fips={FIPS}`
  returns XML carrying a `returnURL` to a state GeoTIFF.

### The PRISM 4 km grid, confirmed

Upper-left origin (−125.0208333, 49.9375), cell 1/24°. Verified against the
archived data — lon −79.875 → col 1083, lat 42.25 → row 184:

```
col = floor((lon + 125.0208333) * 24)
row = floor((49.9375 - lat) * 24)
lon = -125.0208333 + (col + 0.5) / 24
lat =   49.9375    - (row + 0.5) / 24
```

This means grid cells can be generated for any bounding box without a shapefile,
which removes the dependence on the per-state mesh files in `archives/data/`.

## Plan

### Phase 1 — `applebee/acquire/` package
- [ ] `grid.py` — PRISM 4 km cell generation for a bounding box or state list
- [ ] `prism.py` — download daily `.bil`, cache, extract to the wide CSV layout
      `weather.py` already reads
- [ ] `cdl.py` — download CDL per state-year, mosaic, reclassify with Koh,
      buffer-extract to `Forage_spring_{1,3,5}km`
- [ ] Keep output schemas byte-compatible with the existing inputs so nothing
      downstream changes

### Phase 2 — drivers and provenance
- [ ] `scripts/fetch_prism.py` and `scripts/build_forage.py`
- [ ] Write a provenance record beside each output (source URL, retrieval date,
      CDL vintage, code version)
- [ ] Resumable: skip work already on disk, so an interrupted multi-year run
      continues rather than restarts

### Phase 3 — validation
- [ ] Regression test pinning the reproduction of `forage.csv` 2021 above
- [ ] Compare newly fetched PRISM against the archived PA export for overlapping
      days
- [ ] Document expected volumes before anyone starts a large fetch

### Phase 4 — the Northeast run
- [ ] Fetch weather 2008–2024 and forage 2008–2023 for the NE states
- [ ] Rerun the simulation section of
      `notebooks/applebee_evaluation_and_simulation.ipynb` with `REGION_CELLS`
      widened

## Decisions taken

- **Compute forage locally rather than via beeshiny.** The service is a manual
  batch upload; local computation is scriptable, reproducible and validated
  above at r ≥ 0.985.
- **Mosaic CDL across states before extraction**, per the border finding.
- **Cache aggressively and never re-download.** PRISM asks that clients not
  repeatedly fetch the same file.

## Open questions

1. **Which states count as "the Northeast"?** Affects volume by several fold.
2. **Disk budget.** PA alone is 2.3 GB of PRISM CSV and 717 MB of cache; a
   10-state region at 17 years is order 25 GB unless stored as parquet/float32
   from the start. Worth changing the on-disk format while building this.
3. Should the wide-CSV intermediate be skipped entirely and the cache written
   directly? It exists only because that is what the archive produced.

## Progress / outcome

Phase 1 built and validated. `applebee/acquire/` holds `grid.py`, `prism.py`,
`cdl.py`; `tests/test_acquire.py` adds 15 tests (suite now 51, all passing).

### Validated

- **Grid** — reproduces the `(col, row)` index and centroid of **all 7,452**
  archived Pennsylvania cells exactly (max centroid error 4e-8°). So newly
  acquired cells key identically to the existing data, with no translation.
- **CDL → forage** — reproduces `archives/data/forage.csv` for 2021 at
  **r = 0.985 / 0.990 / 0.992** (1/3/5 km), mean absolute difference
  0.015 / 0.011 / 0.009. Pinned as a regression test.
- **Out-of-raster buffers return NaN, not 0** — pinned by a test, because a
  silent zero reads as "no floral resources" rather than "no data", which is
  exactly the failure mode of archived defect 5.

### PRISM rate limiting — hit during testing

Their documented policy, retrieved from the web service PDF:

> Download activity is continuously monitored. To prevent rogue download scripts
> from exceeding bandwidth limits, **if a file is downloaded twice in a 24-hour
> period, no more downloads of that file will be allowed during that period.
> Repeated excessive download activity may result in IP address blocking.**

The endpoint was verified working (a probe returned a valid 2.1 MB zip), but a
subsequent `download_range` burst at the original 0.5 s pause tripped the limiter
and **this IP is now refused at the TCP level**. A block presents as a connect
timeout, not an HTTP error, which is what made it confusing.

The module was hardened in response:

- default pause raised 0.5 s → **3.0 s**
- split connect/read timeouts `(10, 180)` so a block surfaces in seconds
- a `RateLimited` exception distinguishing throttling from a genuine failure
- `download_range` **aborts after three consecutive rate-limit responses**
  rather than continuing to hammer a service that blocks IPs
- `estimate()` reports volume and duration **without making any request**
- no test touches the network

A Northeast 17-year two-variable fetch estimates at **12,420 variable-days,
~25 GB, ~15.5 hours** at the safe pace. That is an overnight job, and it must be
run once and cached — the two-per-24-hours rule makes casual re-running costly.

### Scoping decision: 6 years, not 17 (2026-08-06)

Scoped to **weather years 2013–2018**, which produce offspring springs 2014–2019
— exactly the Turley evaluation window, so the simulation and the evaluation
cover the same period.

**Each PRISM download is a CONUS-wide raster** (621 × 1405, −125 to −66.5 °E),
confirmed by opening an archived `.bil`. Download volume therefore depends *only
on the number of days*, never on the region requested: the whole Northeast costs
exactly what Pennsylvania costs. Only the cache size scales with cells.

| Scope | variable-days | download | on disk | hours |
|---|---|---|---|---|
| 17 years, full calendar (original plan) | 12,420 | 25.5 GB | 43.7 GB | 15.5 |
| **6 years, full calendar** | **4,382** | **9.0 GB** | 15.4 GB | **5.5** |
| 6 years, 1 Jan – 1 Oct only | 3,288 | 6.7 GB | 11.6 GB | 4.1 |

The Jan–Oct trim saves a further 2.3 GB but would break `WeatherGrid.year_series`,
which requires a full 365/366-day window for the emergence search. Not worth
touching model code for; full calendar years it is.

**`--discard-rasters` collapses the on-disk cost to the cache alone** — 0.90 GB
per variable for all 102,555 Northeast cells, so 1.8 GB kept against 9 GB
transferred. The trade is that a different extent cannot be re-sampled later
without re-fetching, which PRISM's two-per-24-hours rule makes expensive. Default
is to keep the rasters.

CDL is a separate one-off: 16 mosaicked states × 6 years ≈ 5.6 GB, producing a
single ~10 MB index.

### One-week fetch attempt (2026-08-06): PRISM still blocked, CDL proven live

**PRISM is still refusing this IP.** Diagnosed with curl against four hosts:

| Host | Result |
|---|---|
| `services.nacse.org` (PRISM data) | **000 — connect fails** |
| `prism.oregonstate.edu` | 200 in 0.12 s |
| `nassgeodata.gmu.edu` (CDL) | 200 in 0.04 s |
| `github.com` | 200 in 0.03 s |

So it is specific to the PRISM data endpoint, not a network problem, and it has
not lifted within the hour. PRISM lifts blocks at their discretion; the fetch
must wait. **The PRISM path is therefore still unproven end to end** — the code
is written and the endpoint was verified working before the block, but no
download has completed through `fetch_and_sample`.

**The CDL half is proven live.** Downloaded Delaware 2013 (15.8 MB) in 3 s and
computed 578 cells × 3 radii in 3 s, straight off the arithmetic grid with no
shapefile.

### Finding: CDL class 0 silently zeroes border cells

Delaware exposed a defect the Pennsylvania validation could not. A state CDL
raster fills everything outside the state line with class 0, "Background", which
the Koh table scores 0.0. Treating that as real barren ground drags border cells
down hard:

- **288 of 565** Delaware cells had >5% Background in their 1 km buffer
- for those, the index read **0.049** instead of **0.380** — understated by 0.158
- unaffected interior cells averaged 0.399

This is the same class of defect as archived defect 5: missing data silently
becoming a plausible-looking number. Fixed with `background_as_nodata=True`
(now the default), which excludes class 0 and renormalises over the remaining
area. Verified not to move interior cells — the Pennsylvania validation is
**identical to four decimals** either way (r = 0.9853 / 0.9896 / 0.9920), and a
buffer that is entirely Background now returns NaN rather than 0.

Mosaicking the adjoining states remains the proper fix for a *state* border;
renormalising is what handles a true edge such as a coastline. Both are in place.

### Northeast forage built, 2013–2018 — with one incomplete year (2026-08-06)

`data/inputs/forage/northeast_forage_spring_lonsdorf.csv` — 615,330 cell-years,
102,555 cells, 2013–2018. Per-year partials kept in
`data/inputs/forage/northeast_forage_by_year/`, so a rerun only redoes what is
missing. All CDL rasters were discarded after each year; disk ended at 18 GB free.

| Year | Rasters | Scored cells | Mean | Status |
|---|---|---|---|---|
| 2013 | 16/16 | 44,231 | 0.539 | complete |
| 2014 | 16/16 | 44,231 | 0.537 | complete |
| 2015 | 16/16 | 44,231 | 0.540 | **complete after rebuild** |
| 2016 | 16/16 | 44,231 | 0.539 | complete |
| 2017 | 16/16 | 44,231 | 0.539 | complete |
| 2018 | 15/16 | 44,045 | 0.537 | missing Rhode Island (358 cells, 0.3%) |

**2015 was rebuilt on 2026-08-06 and now matches every other year at 44,231
cells.** The retry logic recovered all ten states that had failed; the download
took 2,071 s against 208 s for a clean year, which is the retries doing their
job. Only the per-year partial for 2015 was deleted, so the other five years
were reused from cache and cost nothing.

Cross-checked against the archived Pennsylvania index on the 43,212 overlapping
cell-years: **r = 0.979 / 0.978 / 0.976** at 1/3/5 km, mean absolute difference
0.011-0.014. `ForageGrid.load()` reads the file unmodified.

Index range 0.000–0.697, matching the archived Pennsylvania index exactly. 60% of
cells are NaN because the bounding box covers ocean, Canada and land beyond the
16 mosaicked states; `--clip-to-states` gives a land-only cell set instead.

**2015 lost ten of sixteen states to transient service timeouts** — the same
states downloaded without trouble in every other year, and the failures consumed
876 s, so this reads as service flakiness rather than missing data. 2018 lost
only Rhode Island.

Two fixes made in response:

- `download_many` now **retries each state-year three times with widening
  backoff** instead of recording the first failure and moving on.
- `coverage_report` plus a loud warning in `build_forage.py`. This mattered
  because **a year that loses rasters still produces full-length rows** — the
  gaps are NaN, not absent rows — so nothing about the file's shape reveals the
  problem. Only comparing scored counts across years does. Without the check,
  2015 would have entered the simulation looking like a real half-empty region.

**To finish (needs wifi, not mobile data):** delete
`northeast_forage_by_year/2015.csv` and rerun `--years 2015 2015`; optionally
`2018.csv` for Rhode Island. About 2.3 GB each.

### Both datasets complete (2026-08-07)

**PRISM weather 2013–2018, Northeast: done and validated.** 2,187 days fetched
per variable plus 4 already held = 2,191, **zero missing**, both `tmean` and
`ppt`. Verified against the archived Pennsylvania export on 7,452 shared cells ×
129 sampled days: **max absolute difference 0.0000000000, 100.0000% exactly
equal**, both variables, no NaN on either side.

Two defects surfaced and were fixed:

- **PRISM changed delivery format.** The service now returns GeoTIFF
  (`prism_tmean_us_25m_20150501.tif`) where the archive holds ESRI BIL. The
  reader globbed only `*.bil`, so every sampled value came back NaN. Compared
  directly: same 621 × 1405 grid, same bounds and nodata, **max difference
  0.000000 °C over 481,631 cells** — only the container changed. Both formats
  are now read. ("25m" is 2.5 arc-minutes, not 25 metres.)
- **A dropped connection killed the first run** after eight days, because only
  `RateLimited` was caught. `fetch_with_retry` now handles transient network
  faults with widening backoff, and a run stops only after five consecutive
  failures.

**Forage 2013–2018, Northeast: done.**

| Year | Source | Scored | Mean |
|---|---|---|---|
| 2013–2017 | 16-state mosaic | 44,231 each | 0.537–0.540 |
| 2018 | **national CDL** | **44,759** | 0.535 |

### The national CDL is the better source, and should replace the state mosaic

The GMU per-state service failed repeatedly — ten states lost in 2015, seven in
2018 — then went down entirely (503, then hanging). Diagnosed as *their* outage,
not an IP block: the same host answered `/`, `/CropScape/` and `/axis2/services/`
in ~0.1 s while only the CDL endpoint stalled, and the 503 was a stock Apache
page rather than a block notice.

USDA serves the CONUS-wide CDL from their own host: `~1.9 GB` zipped per year,
downloaded and extracted in **174 s**. Against the 16-state mosaic it is:

- **more complete** — 44,759 cells against 44,231, gaining 528 and losing none,
  because there are no state-border gaps
- **more accurate** — validated against the archived Pennsylvania index at
  r = 0.979 / 0.978 / 0.976 (1/3/5 km) versus the mosaic's 0.973 / 0.970 / 0.966
- **simpler** — no mosaic, no Background padding to renormalise, no 16-way
  retry loop, no dependence on a service that keeps falling over

### Whole series rebuilt from the national CDL (2026-08-07)

`--source national` is now the **default**, and all six years were rebuilt from
it so the series comes from one source. Existing per-year files were backed up to
`forage/_backup_state_mosaic/` first — the earlier loss of a good 2018 came from
deleting a partial without one.

| | before (mosaic) | after (national) |
|---|---|---|
| Cells scored, per year | 44,231 (2018: 21,777) | **44,759, every year** |
| Same cells in all years | no | **yes** |
| vs archived PA index, 1 km | r = 0.973–0.985 | r = 0.973–0.981 |

Four checks after the rebuild:

1. **Every year covers exactly the same 44,759 cells** — an exactly balanced
   panel, which the mosaic never achieved.
2. Per-year validation against the archived Pennsylvania index: r = 0.973–0.981
   at 1 km, mean absolute difference 0.012–0.015. (2017 matches on only 5,992
   cells rather than 7,444 because the *archived* index is itself short 1,452
   Pennsylvania cells that year — the known 2017 CDL gap, not a new problem.)
3. **National vs mosaic where both scored a cell: r = 0.9995, mean absolute
   difference 0.0001** over 221,155 cell-years. The rebuild added coverage
   without shifting values.
4. Year-to-year stability r = 0.992–0.995, mean absolute change 0.007–0.009.

Cost: five national rasters at ~3 GB each, ~200 s download and ~515 s compute per
year, about an hour total.

### Scale finding

The Northeast bounding box holds **102,555 cells, 13.8× Pennsylvania** — but that
includes ocean and Canada. `grid.cells_for_states()` clips to real state
boundaries and should be used instead; open question 2 in this plan (disk budget)
should be settled before Phase 4.

## Commits

| SHA | Date | Subject |
|---|---|---|
| _pending_ | | |

## Follow-ups

- Supersedes the "extending step 3" section of the evaluation notebook.
