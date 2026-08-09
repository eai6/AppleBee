"""Run AppleBee across the Northeast, 2013-2018 weather -> 2014-2019 offspring.

Uses the inputs acquired by ``applebee.acquire``: PRISM daily weather from
``data/inputs/weather/northeast/`` and the national-CDL forage index from
``data/inputs/forage/``. Both cover exactly the same 44,759 grid cells in every
year, so the panel is balanced.

    python scripts/run_northeast_simulation.py

Writes outputs/northeast_simulation.parquet and summary tables.
"""

from __future__ import annotations

import sys
import time
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from applebee import AppleBee, ForageGrid, ModelParams  # noqa: E402
from applebee import config  # noqa: E402
from applebee.config import OUTPUTS, TABLES  # noqa: E402
from applebee.weather import load_matrices  # noqa: E402

warnings.filterwarnings("ignore")

WEATHER_YEARS = range(2013, 2019)  # -> offspring springs 2014-2019

REGIONS = {
    "northeast": (config.NE_WEATHER_DIR, config.NE_TMEAN_KEY, config.NE_PPT_KEY,
                  config.NE_FORAGE_CSV),
    "conus": (config.CONUS_WEATHER_DIR, config.CONUS_TMEAN_KEY, config.CONUS_PPT_KEY,
              config.CONUS_FORAGE_CSV),
}


def main() -> None:
    region = sys.argv[1] if len(sys.argv) > 1 else "northeast"
    if region not in REGIONS:
        raise SystemExit(f"region must be one of {sorted(REGIONS)}")
    weather_dir, tmean_key, ppt_key, forage_csv = REGIONS[region]
    print(f"region: {region}")
    tmean = load_matrices(weather_dir, tmean_key)
    ppt = load_matrices(weather_dir, ppt_key)
    forage = ForageGrid.load(forage_csv)

    # Only cells with both weather and a forage index can be run.
    weather_cells = {(int(c), int(r)) for c, r in zip(tmean.cells["col"], tmean.cells["row"])}
    cells = [cell for cell in forage.cells if cell in weather_cells]
    print(f"weather {tmean.n_cells:,} cells x {len(tmean.dates):,} days")
    print(f"forage  {len(forage.cells):,} cells")
    print(f"runnable {len(cells):,} cells x {len(list(WEATHER_YEARS))} years "
          f"= {len(cells) * len(list(WEATHER_YEARS)):,} cell-years\n")

    model = AppleBee(tmean, ppt, forage, ModelParams())
    started = time.time()
    results, failures = model.run(cells, WEATHER_YEARS, progress=True)
    print(f"\n{len(results):,} cell-years in {time.time() - started:.0f}s, "
          f"{len(failures):,} failed")
    if len(failures):
        print(failures["error"].value_counts().head().to_string())

    # Attach coordinates for mapping.
    coords = tmean.cells[["col", "row", "lon", "lat"]]
    results = results.merge(coords, on=["col", "row"], how="left")

    OUTPUTS.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)
    results.to_parquet(OUTPUTS / f"{region}_simulation.parquet")

    by_year = results.groupby("offspring_year").offspring.agg(
        ["mean", "std", "min", "max"]).round(3)
    per_cell = results.groupby(["col", "row"]).offspring.agg(["mean", "std"])
    by_year.to_csv(TABLES / f"{region}_by_year.csv")

    print("\n=== offspring per female ===")
    print(f"  max {results.offspring.max():.1f}   mean {results.offspring.mean():.2f}   "
          f"min {results.offspring.min():.2f}")
    print(f"  variability through time (mean within-cell SD): {per_cell['std'].mean():.2f}")
    print(f"  variability across space (SD of cell means)   : {per_cell['mean'].std():.2f}")
    print("\n=== by year ===")
    print(by_year.to_string())
    print(f"\nworst {by_year['mean'].idxmin()}, best {by_year['mean'].idxmax()}")
    print(f"\nwrote {OUTPUTS / (region + '_simulation.parquet')}")


if __name__ == "__main__":
    main()
