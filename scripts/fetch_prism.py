"""Fetch daily PRISM weather and cache it for a region.

Each PRISM file is a **CONUS-wide** raster, so download volume depends only on
the number of days -- the Northeast costs exactly what Pennsylvania costs. Only
the cache size depends on how many cells are kept.

    # see the cost first; makes no network request
    python scripts/fetch_prism.py --start 2013-01-01 --end 2018-12-31 --dry-run

    # then fetch (hours; safe to interrupt and rerun)
    python scripts/fetch_prism.py --start 2013-01-01 --end 2018-12-31 --region northeast

PRISM allows two downloads of a file per 24 hours and blocks IPs for excessive
activity, so this paces itself and stops after three consecutive refusals.
Anything already on disk is reused, so rerunning resumes rather than restarts.

``--discard-rasters`` deletes each raster once sampled, holding disk to the cache
alone. That trades away the ability to re-sample a different extent later without
re-fetching, so the default keeps them.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from applebee.acquire import grid, prism  # noqa: E402
from applebee.config import CACHE, DATA  # noqa: E402

REGIONS = {"northeast": grid.NORTHEAST, "pennsylvania": grid.PENNSYLVANIA,
           "conus": grid.CONUS}

# Any PRISM day serves as the land mask -- it is identical across days.
LAND_MASK_RASTER = (
    Path(__file__).resolve().parent.parent
    / "archives/data/prism/PRISM_tmean_stable_4kmD2_20150501_bil"
    / "PRISM_tmean_stable_4kmD2_20150501_bil.bil"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", default="2013-01-01", help="first day (default: %(default)s)")
    parser.add_argument("--end", default="2018-12-31", help="last day (default: %(default)s)")
    parser.add_argument("--region", default="northeast", choices=sorted(REGIONS))
    parser.add_argument("--variables", nargs="+", default=["tmean", "ppt"],
                        choices=list(prism.VARIABLES))
    parser.add_argument("--clip-to-states", action="store_true",
                        help="clip cells to real state boundaries instead of the bounding box "
                             "(smaller cache; needs a one-off boundary download)")
    parser.add_argument("--discard-rasters", action="store_true",
                        help="delete each raster once sampled, keeping only the cache")
    parser.add_argument("--pause", type=float, default=prism.DEFAULT_PAUSE_SECONDS,
                        help="seconds between requests (default: %(default)s)")
    parser.add_argument("--raster-dir", type=Path, default=DATA / "raw" / "prism")
    parser.add_argument("--dry-run", action="store_true", help="report cost and exit")
    args = parser.parse_args()

    region = REGIONS[args.region]
    days = pd.date_range(args.start, args.end, freq="D")

    report = prism.estimate(args.raster_dir, tuple(args.variables), args.start, args.end)
    print(f"region      : {region.name}")
    print(f"period      : {args.start} .. {args.end}  ({len(days):,} days)")
    print(f"variables   : {', '.join(args.variables)}")
    print(f"to download : {report['to_download']:,} variable-days "
          f"(~{report['approx_GB']:.1f} GB, ~{report['approx_hours_at_default_pause']:.1f} h)")
    print(f"already held: {report['already_held']:,}")

    if args.region == "conus":
        # Ocean and beyond-border cells carry no data in any PRISM day, so
        # sampling them would double the cache to no purpose.
        cells = grid.land_cells(LAND_MASK_RASTER)
        print("cells       : CONUS land mask (ocean and nodata excluded)")
    elif args.clip_to_states:
        print(f"\nresolving state boundaries for {len(region.states)} states ...")
        cells = grid.cells_for_states(region.states)
    else:
        cells = region.cells()
    cache_gb = len(cells) * len(days) * 4 / 1e9
    print(f"cells       : {len(cells):,}  -> cache {cache_gb:.2f} GB per variable")

    if args.dry_run:
        print("\ndry run; nothing fetched.")
        return

    # Fetched weather is a *primary* copy -- with the rasters discarded there is
    # nothing local to rebuild it from -- so it must not live in data/cache/,
    # which is documented as disposable.
    destination = DATA / "inputs" / "weather" / region.name
    destination.mkdir(parents=True, exist_ok=True)

    for variable in args.variables:
        key = f"{region.name}_{variable}"
        print(f"\n--- {variable} -> {destination / (key + '.values.npy')}")
        result = prism.fetch_and_sample(
            args.raster_dir, key, cells, variable, args.start, args.end,
            keep_rasters=not args.discard_rasters, pause=args.pause,
            cache_dir=destination,
        )
        print(f"    {result}")

    print(f"\ndone. Load with load_matrices(Path('{destination}'), '{region.name}_tmean').")


if __name__ == "__main__":
    main()
