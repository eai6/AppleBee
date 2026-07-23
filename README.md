# AppleBee

An individual-based, spatially explicit mechanistic model predicting the annual
reproductive success of the solitary bee *Osmia cornifrons* from daily weather
and landscape floral resources.

This is a clean-room reimplementation of Chapter 4 of *Bridging AI and Ecology*
(Amoah, Boyle, Smithwick & Grozinger). The original exploratory code is kept
unchanged in `archives/`; see [`docs/REPLICATION_NOTES.md`](docs/REPLICATION_NOTES.md)
for the results comparison and for the defects found in it.

## The model

Four sub-models, driven by PRISM daily mean temperature and precipitation on a
4 km grid plus a Lonsdorf spring floral resource index:

| Sub-model | Equations | What it produces |
|---|---|---|
| Emergence date | 4.1 | Day a female emerges, by degree-day accumulation |
| Egg production | 4.2–4.3 | Eggs laid over a 20-day foraging period |
| Egg and larva mortality | 4.4–4.6 | Risk from days outside the 10–30 °C window |
| Winter mortality | 4.7–4.8 | Risk from warm pre-winter days (15 Aug – 1 Oct) |

Combined by Equation 4.10: `R = E × (1 − M) × (1 − W)`.

Offspring produced in weather year *Y* are the adults counted in spring *Y+1*.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/build_cache.py     # parse PRISM CSVs -> cached matrices
```

`build_cache.py` reads the ~2.4 GB of wide PRISM CSVs in `archives/output/` once
and writes float32 matrices to `data/cache/` (~720 MB). Everything downstream
reads the cache. All input data is already in `archives/` — nothing to download.

## Running

```bash
# Objective 4: statewide simulation, 7,452 cells x 16 years (~20 s)
.venv/bin/python scripts/run_pa_simulation.py --params default
.venv/bin/python scripts/run_pa_simulation.py --params calibrated

# Objective 4 analysis: summary stats, random forest, no-egg-day t-test
.venv/bin/python scripts/analyse_pa_simulation.py

# Objective 2: Sobol sensitivity of the egg-production sub-model
.venv/bin/python scripts/run_sobol.py --n 512

# All figures
.venv/bin/python scripts/make_figures.py
```

Results land in `outputs/` — `pa_simulation_*.parquet`, `tables/*.csv`, and
`figures/*.png`.

## Using the model directly

```python
from applebee import AppleBee, ForageGrid, ModelParams, load_weather
from applebee.config import PA_FORAGE_CSV, PA_PPT_CSV, PA_TMEAN_CSV

model = AppleBee(
    tmean=load_weather(PA_TMEAN_CSV, "pa_tmean"),
    ppt=load_weather(PA_PPT_CSV, "pa_ppt"),
    forage=ForageGrid.load(PA_FORAGE_CSV),
    params=ModelParams(),          # literature values, Tables 4-1 to 4-4
)

result = model.run_grid_year(col=1146, row=240, year=2018)
print(result.offspring, result.eggs, result.emergence_date)
```

`ModelParams` is frozen; vary parameters with
`ModelParams().with_(temperature_threshold=18.72)` or use
`ModelParams.calibrated()` for the thresholds tuned on Centrella et al. (2020).

## Layout

```
applebee/
  config.py      model parameters (each traceable to the chapter) and paths
  weather.py     PRISM loader; wide CSV -> cached (n_cells x n_days) matrices
  forage.py      spring floral resource index, with audited fallbacks
  submodels.py   Equations 4.1-4.10 as pure functions
  model.py       lifecycle orchestration over cells and years
  evaluation/    centrella.py (Objective 2), turley.py (Objective 3)
scripts/         cache build, simulation, analysis, figures
tests/           sub-model tests pinned to the chapter's worked examples
archives/        original exploratory code and all source data (unmodified)
```

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

The tests pin each sub-model to the numeric examples stated in the chapter —
one extreme day giving 10% egg mortality, five giving 50%, sixty warm
pre-winter days giving 15% winter mortality — plus the threshold boundary
conditions, which is where the archived implementation diverged.

## Known gap

The Objective 2 evaluation does not reproduce the chapter's absolute R²,
because the archived Centrella et al. (2020) extract records emerged adults
rather than the brood-cell counts the chapter describes. See §3 of the
replication notes.
