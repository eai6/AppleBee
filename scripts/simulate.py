"""Run AppleBee over any configured region.

Replaces the per-region scripts. A run is now (dataset, years, parameters), where
the dataset says where the inputs are and the parameters can come from a file, so
the whole configuration is a command line plus a text file rather than an edit to
the code.

    python scripts/simulate.py --list
    python scripts/simulate.py --region pennsylvania
    python scripts/simulate.py --region conus --years 2013 2018
    python scripts/simulate.py --region northeast --params calibrated
    python scripts/simulate.py --region conus --params my_run.toml --dry-run

``--params`` takes ``default``, ``calibrated``, or a path to JSON/TOML naming only
the parameters to change:

    # my_run.toml
    temperature_threshold = 18.72
    longevity = 24

Writes ``outputs/{region}_simulation.parquet`` plus a summary table, and a JSON
record of the exact parameters used beside them.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from applebee import datasets  # noqa: E402
from applebee.config import OUTPUTS, TABLES, ModelParams  # noqa: E402


def resolve_params(spec: str) -> ModelParams:
    if spec == "default":
        return ModelParams()
    if spec == "calibrated":
        return ModelParams.calibrated()
    path = Path(spec)
    if not path.exists():
        raise SystemExit(f"--params must be 'default', 'calibrated', or a file; {spec!r} not found")
    return ModelParams.from_file(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--region", default="pennsylvania",
                        help="dataset name (see --list)")
    parser.add_argument("--years", nargs=2, type=int, metavar=("FIRST", "LAST"),
                        help="inclusive weather years; defaults to everything the dataset covers")
    parser.add_argument("--params", default="default",
                        help="'default', 'calibrated', or a JSON/TOML file")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--list", action="store_true", help="show datasets and exit")
    parser.add_argument("--dry-run", action="store_true", help="report the plan and exit")
    args = parser.parse_args()

    if args.list:
        pd.set_option("display.width", 200, "display.max_columns", 20)
        print(datasets.describe().to_string(index=False))
        return

    dataset = datasets.get(args.region)
    dataset.require()
    params = resolve_params(args.params)

    covered = dataset.weather_years()
    years = range(args.years[0], args.years[1] + 1) if args.years else covered
    outside = [y for y in years if y not in covered]
    if outside:
        raise SystemExit(
            f"{dataset.name} covers weather years {covered.start}-{covered.stop - 1}; "
            f"{outside[0]}-{outside[-1]} is outside that."
        )

    cells = dataset.cells()
    changed = params.differences()
    print(f"region     : {dataset.name} — {dataset.description}")
    print(f"cells      : {len(cells):,} with both weather and forage")
    print(f"years      : weather {years.start}-{years.stop - 1} "
          f"-> offspring springs {years.start + 1}-{years.stop}")
    print(f"cell-years : {len(cells) * len(list(years)):,}")
    print(f"parameters : {args.params}"
          + (f" — {len(changed)} differ from the literature defaults" if changed else " (literature values)"))
    for name, (was, now) in changed.items():
        print(f"               {name}: {was} -> {now}")

    if args.dry_run:
        print("\ndry run; nothing computed.")
        return

    model = dataset.model(params)
    started = time.time()
    results, failures = model.run(cells, years, progress=True)
    print(f"\n{len(results):,} cell-years in {time.time() - started:.0f}s, {len(failures):,} failed")
    if len(failures):
        print(failures["error"].str.split(":").str[0].value_counts().to_string())

    coords = model.tmean.cells[["col", "row", "lon", "lat"]]
    results = results.merge(coords, on=["col", "row"], how="left")

    OUTPUTS.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)
    stem = args.out.stem if args.out else f"{dataset.name}_simulation"
    parquet = (args.out or OUTPUTS / f"{stem}.parquet")
    results.to_parquet(parquet)
    # The exact parameters, beside the results, so a run is reproducible.
    params.to_file(parquet.with_suffix(".params.json"))

    by_year = results.groupby("offspring_year").offspring.agg(["mean", "std", "min", "max"]).round(3)
    by_year.to_csv(TABLES / f"{stem}_by_year.csv")
    per_cell = results.groupby(["col", "row"]).offspring.agg(["mean", "std"])

    print("\n=== offspring per female ===")
    print(f"  max {results.offspring.max():.1f}   mean {results.offspring.mean():.2f}   "
          f"min {results.offspring.min():.2f}")
    print(f"  variability through time (mean within-cell SD): {per_cell['std'].mean():.2f}")
    print(f"  variability across space (SD of cell means)   : {per_cell['mean'].std():.2f}")
    print("\n=== by year ===")
    print(by_year.to_string())
    print(f"\nworst {by_year['mean'].idxmin()}, best {by_year['mean'].idxmax()}")
    print(f"\nwrote {parquet}\n      {parquet.with_suffix('.params.json')}")


if __name__ == "__main__":
    main()
