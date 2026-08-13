# Simulation inputs

Everything the AppleBee model reads, in one place. Before this folder existed the
inputs were scattered across four directories inside `archives/`, all of which
`.gitignore` excludes — so the model's actual inputs were untracked and hard to
review. `archives/` is now a historical reference only; `applebee/config.py`
points here.

Nothing in this folder is derived. Derived artefacts live in `data/cache/`
(parsed PRISM matrices, rebuilt by `scripts/build_cache.py`) and `outputs/`.

## Contents

```
data/inputs/
  weather/       daily PRISM temperature and precipitation, 4 km grid
    pennsylvania/  new_york/  northeast/  conus/
  forage/        Lonsdorf spring floral resource index, by region
  observations/  field datasets the model is evaluated against
```

Nothing here depends on `archives/`. Files too large for git carry a
`PROVENANCE.json` alongside — source, coverage, validation and a SHA-256 per
file — and those records *are* tracked, so integrity is checkable and a rebuild
is documented even where the bytes cannot be committed.

---

## weather/

Daily PRISM 4 km temperature and precipitation, grouped by region. Large extents
are stored as **float32 matrices** (`{key}.values.npy` + `.dates.npy` +
`.cells.parquet`), read with `applebee.weather.load_matrices`; small ones stay as
the source CSV, read with `load_weather`.

| Region | Form | Cells | Days | Coverage | Size |
|---|---|---|---|---|---|
| `pennsylvania/` | matrices | 7,452 | 12,601 | 1990-01-01 – 2024-07-01 | 716 MB |
| `new_york/` | CSV | 17 sites | 61 | 2015-05-01 – 2015-06-30 | 40 KB |
| `northeast/` | matrices | 102,555 | 2,191 | 2013-01-01 – 2018-12-31 | 1.7 GB |
| `conus/` | matrices | 481,631 | 2,191 | 2013-01-01 – 2018-12-31 | 8.4 GB |

Every region carries a `PROVENANCE.json` recording its source, coverage,
validation and a SHA-256 per file. Those are tracked in git; the matrices are not.

**Pennsylvania was converted from CSV to matrices** so that `data/inputs/` no
longer depends on `archives/`, which is excluded from git. It previously appeared
here as two symlinks into `archives/output/`, which dangle in a fresh clone. The
conversion is lossless — verified **max difference 0.0, 100.0000% exactly equal**
against the original export — and takes 2.45 GB of wide CSV down to 716 MB. The
raw CSVs remain in `archives/output/` for anyone who wants them.

Read it with:

```python
from applebee.weather import load_pennsylvania, load_matrices
tmean = load_pennsylvania("tmean")                     # Pennsylvania
conus = load_matrices(CONUS_WEATHER_DIR, "conus_ppt")  # any other region
```

Column order in the source CSVs is **not** chronological, and some days appear
twice under different PRISM release tags (`early`, `provisional`, `stable`). The
parser sorts by date and keeps the most quality-controlled release of each
duplicated day — see `applebee/weather.py:34`.

## forage/

Lonsdorf et al. (2009) spring floral resource index, scored from USDA Cropland
Data Layer classes with Koh et al. (2016) expert weights and averaged over a
foraging radius. Runs 0–1; the model calls a cell forage-abundant at or above
`L_H` (default 0.5). Read by `applebee/forage.py`.

| File | Rows | Unit | Coverage |
|---|---|---|---|
| `pa_forage_spring_lonsdorf.csv` | 117,780 | 7,452 grid cells × year | 2008–2023 |
| `ny_forage_spring_2015_sites.csv` | 51 | 17 sites × 3 radii | spring 2015 |

`pa_forage_spring_lonsdorf.csv` — columns `lon, lat, col, row, year,
Forage_spring_1km, Forage_spring_3km, Forage_spring_5km`. The model uses the
**1 km** radius. Observed range 0.000–0.697; the index never reaches 1 anywhere
in Pennsylvania, so the 0.5 threshold sits well inside the realised
distribution rather than at its edge.

**2017 is short by 1,452 cells** (6,000 of 7,452) — a Cropland Data Layer gap.
`ForageGrid.get` falls back to the nearest available year *for the same cell* and
records every substitution in `ForageGrid.fallbacks`.

`ny_forage_spring_2015_sites.csv` — columns `Site, Long, Lat, class, radius,
season, year, value`. Filtered to `radius == "1km"` and `season == "spring"` to
match the Pennsylvania index.

Upstream, not used directly: `archives/data/forage/foragesummary_*.csv` (the
per-cell CDL summaries this file was built from) and `archives/data/CDL/`
(`cdl_reclass_koh.csv`, the class-to-weight table).

## observations/

Field data the model is evaluated against.

### `centrella_2020_ny_orchards.csv` — Objective 2

Centrella et al. (2020). 17 Finger Lakes apple orchards, each stocked with
*O. cornifrons* nest tubes on 5 May 2015; emergence began 7 May. 51 rows
(17 sites × 3 collection time points), 88 columns.

Columns the model uses: `Site_Code`, `Time_Point`, `Calendar_Date`,
`Total_Emerged_Males`, `Total_Emerged_Females`, `Proportion_Larval_Mortality`.

The rest are land-cover proportions at eight radii, pollen-provision
composition, pesticide risk indices and floral diversity metrics — none used.

**This file does not contain the response variable the chapter used.** It records
emerged adults; the chapter counts brood cells. See §3 of
`docs/REPLICATION_NOTES.md` — this is the sole reason Objective 2 does not
reproduce.

### `turley_2022_pa_blue_vane.csv` — Objective 3

Turley et al. (2022), Dryad `doi:10.5061/dryad.9kd51c5mc`. Blue vane trap
collections at eight locations around the Penn State Fruit Research and
Extension Center, Adams County PA, weekly April–October.

26,716 specimen rows, 2014–2019, 30 genera. **183 are *Osmia*** — the model's
response is the annual count of those, six numbers in total.

---

---

## Northeast, 2013–2018 — acquired by `applebee/acquire/`

Added 2026-08. Unlike everything above, these were fetched from source rather
than inherited from the archive. Together they let the simulation run beyond
Pennsylvania.

### `weather/northeast/` — daily PRISM, **not a cache**

`northeast_tmean.*` and `northeast_ppt.*` — **102,555 cells × 2,191 days**
(2013-01-01 – 2018-12-31), float32 matrices plus a date index and cell table.
857 MB per variable. Read with `applebee.weather.load_matrices`.

**This is a primary copy with no local source to rebuild from.** The PRISM
rasters were discarded after sampling, so deleting it costs a ~9 GB re-download
subject to PRISM's two-fetches-per-file-per-24-hours limit. It deliberately sits
outside `data/cache/`, which *is* disposable. `PROVENANCE.json` beside it records
the source URL, retrieval date, grid definition and a SHA-256 per file.

Validated against the archived Pennsylvania export on 7,452 shared cells × 129
sampled days: **max absolute difference 0.0000000000, 100.0000% exactly equal**,
both variables.

Note PRISM now delivers GeoTIFF (`prism_tmean_us_25m_20150501.tif`) where the
archive holds ESRI BIL — verified bit-identical, same 621 × 1405 grid. "25m" is
2.5 arc-minutes, not 25 metres.

### `forage/northeast_forage_spring_lonsdorf.csv`

615,330 cell-years — **44,759 scored cells in every one of the six years**, an
exactly balanced panel. Index range 0.000–0.697, matching the Pennsylvania
index. Per-year partials in `northeast_forage_by_year/` so a rebuild only redoes
what is missing.

Built from the **USDA national CDL** (`{year}_30m_cdls.zip`, ~1.9 GB), not the
per-state rasters. The per-state route was tried first and abandoned: it lost ten
states from the 2015 build and seven from 2018, then the GMU service returned 503
for a day. National is also *more complete* (+528 cells, none lost, because there
are no state-border gaps) and *more accurate* against the archived Pennsylvania
index (r = 0.980 against 0.973 at 1 km).

Where both methods scored a cell they agree almost exactly — r = 0.9995, mean
absolute difference 0.0001 over 221,155 cell-years — so the rebuild added
coverage rather than shifting values. The superseded mosaic build is kept in
`forage/_backup_state_mosaic/`.

Year-to-year stability runs r = 0.992–0.995 with mean absolute change 0.007–0.009.

---

## Where each file is read

| Module | Reads |
|---|---|
| `applebee/weather.py` | `load_pennsylvania()` for `weather/pennsylvania/`; `load_matrices()` for `northeast/`, `conus/`; `load_weather()` for the New York CSVs |
| `applebee/forage.py` | any `forage/*_forage_spring_lonsdorf.csv` |
| `applebee/evaluation/centrella.py` | New York weather and forage, Centrella observations |
| `applebee/evaluation/turley.py` | Turley observations (+ the model over Pennsylvania) |
| `applebee/acquire/` | writes `weather/{region}/` and `forage/{region}_*.csv` |

Paths are declared in `applebee/config.py`.
