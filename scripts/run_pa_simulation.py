"""Objective 4: long-term simulation of reproductive success across Pennsylvania.

Runs the AppleBee model for every 4 km grid cell and every weather year, and
writes one row per cell-year. Weather years 2008-2023 report offspring for
2009-2024, matching the chapter.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from applebee import AppleBee, ForageGrid, ModelParams, load_weather
from applebee.config import OUTPUTS, PA_FORAGE_CSV
from applebee.weather import load_pennsylvania

FIRST_WEATHER_YEAR = 2008
LAST_WEATHER_YEAR = 2023


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first-year", type=int, default=FIRST_WEATHER_YEAR)
    parser.add_argument("--last-year", type=int, default=LAST_WEATHER_YEAR)
    parser.add_argument(
        "--params",
        choices=["default", "calibrated"],
        default="default",
        help="default = literature values (Tables 4-1..4-4); "
        "calibrated = egg-production thresholds tuned on Centrella et al.",
    )
    parser.add_argument("--limit-cells", type=int, default=None, help="for smoke tests")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    params = ModelParams() if args.params == "default" else ModelParams.calibrated()

    print("loading inputs...", flush=True)
    tmean = load_pennsylvania("tmean")
    ppt = load_pennsylvania("ppt")
    forage = ForageGrid.load(PA_FORAGE_CSV)

    # Only cells present in both the weather grid and the forage grid.
    cells = [c for c in forage.cells if tmean.has_cell(*c)]
    if args.limit_cells:
        cells = cells[: args.limit_cells]
    years = list(range(args.first_year, args.last_year + 1))
    print(f"{len(cells):,} cells x {len(years)} years = {len(cells)*len(years):,} runs", flush=True)

    model = AppleBee(tmean, ppt, forage, params)
    start = time.time()
    results, failures = model.run(cells, years, progress=True)
    elapsed = time.time() - start

    OUTPUTS.mkdir(parents=True, exist_ok=True)
    out = args.out or OUTPUTS / f"pa_simulation_{args.params}.parquet"
    results.to_parquet(out, index=False)

    print(f"\ndone in {elapsed/60:.1f} min -> {out}")
    print(f"  {len(results):,} rows, {len(failures):,} failures")
    if len(failures):
        fail_out = out.with_name(out.stem + "_failures.csv")
        failures.to_csv(fail_out, index=False)
        print(f"  failure reasons: {failures['error'].value_counts().to_dict()}")
        print(f"  written to {fail_out}")
    if forage.fallbacks:
        print(f"  forage nearest-year fallbacks used: {len(forage.fallbacks):,} cell-years")

    if len(results):
        by_year = results.groupby("offspring_year")["offspring"]
        print("\noffspring per female by year:")
        print(by_year.agg(["mean", "std", "min", "max"]).round(2).to_string())


if __name__ == "__main__":
    main()
